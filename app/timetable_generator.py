import random
import time
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Set, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from app.models import (
    Course, Instructor, Room, Timetable, Semester,
    InstructorAvailability, InstructorPreference, TimetableConstraint,
    TimetableGenerationJob
)
from app.schemas import (
    OptimizationStrategyEnum, TimeSlot, ConflictInfo, TimetableStatistics,
    TimetableGenerationResult
)

# Time slot constants
DEFAULT_TEACHING_HOURS = {
    "Monday": {"start": "08:00", "end": "17:00"},
    "Tuesday": {"start": "08:00", "end": "17:00"},
    "Wednesday": {"start": "08:00", "end": "17:00"},
    "Thursday": {"start": "08:00", "end": "17:00"},
    "Friday": {"start": "08:00", "end": "17:00"},
    "Saturday": {"start": "08:00", "end": "13:00"},
    "Sunday": {"start": "00:00", "end": "00:00"}  # Usually no classes
}

DEFAULT_LECTURE_DURATION = 60  # minutes
DEFAULT_LAB_DURATION = 120  # minutes

# Helper functions
def parse_time(time_str: str) -> datetime.time:
    """Convert string time to datetime.time object"""
    hour, minute = map(int, time_str.split(':'))
    return datetime.time(hour=hour, minute=minute)

def time_to_minutes(t: datetime.time) -> int:
    """Convert time to minutes from midnight"""
    return t.hour * 60 + t.minute

def minutes_to_time(minutes: int) -> datetime.time:
    """Convert minutes from midnight to time"""
    hours = minutes // 60
    mins = minutes % 60
    return datetime.time(hour=hours, minute=mins)

def check_time_overlap(start1: datetime.time, end1: datetime.time, 
                      start2: datetime.time, end2: datetime.time) -> bool:
    """Check if two time periods overlap"""
    return max(time_to_minutes(start1), time_to_minutes(start2)) < min(time_to_minutes(end1), time_to_minutes(end2))

def get_available_time_slots(
    day: str,
    duration_minutes: int,
    existing_slots: List[Tuple[datetime.time, datetime.time]],
    day_start: datetime.time,
    day_end: datetime.time,
    step_minutes: int = 30
) -> List[Tuple[datetime.time, datetime.time]]:
    """
    Get available time slots for a specific day given existing bookings
    Returns list of (start_time, end_time) tuples
    """
    available_slots = []
    day_start_minutes = time_to_minutes(day_start)
    day_end_minutes = time_to_minutes(day_end)
    
    # Convert existing slots to minutes
    existing_minutes = [(time_to_minutes(start), time_to_minutes(end)) 
                        for start, end in existing_slots]
    
    # Check each potential time slot
    for start_minutes in range(day_start_minutes, day_end_minutes - duration_minutes + 1, step_minutes):
        end_minutes = start_minutes + duration_minutes
        slot_free = True
        
        for existing_start, existing_end in existing_minutes:
            # Check for overlap
            if max(start_minutes, existing_start) < min(end_minutes, existing_end):
                slot_free = False
                break
        
        if slot_free:
            available_slots.append((
                minutes_to_time(start_minutes),
                minutes_to_time(end_minutes)
            ))
    
    return available_slots

class TimetableGenerator:
    """Class for generating optimized timetables"""
    
    def __init__(
        self,
        db: Session,
        semester_id: int,
        strategy: OptimizationStrategyEnum = OptimizationStrategyEnum.balanced,
        department_ids: List[int] = None,
        programme_ids: List[int] = None,
        respect_existing: bool = True,
        clear_existing: bool = False,
        max_iterations: int = 1000,
        time_limit_seconds: int = 300  # 5 minutes
    ):
        self.db = db
        self.semester_id = semester_id
        self.strategy = strategy
        self.department_ids = department_ids
        self.programme_ids = programme_ids
        self.respect_existing = respect_existing
        self.clear_existing = clear_existing
        self.max_iterations = max_iterations
        self.time_limit_seconds = time_limit_seconds
        
        # Load constraints
        self.constraints = self._load_constraints()
        
        # Initialize counter for new entries
        self.entries_created = 0
        self.conflicts = []
        
        # Create the job record
        self.job = self._create_job()
    
    def _create_job(self) -> TimetableGenerationJob:
        """Create a job record in the database"""
        job = TimetableGenerationJob(
            semester_id=self.semester_id,
            created_at=datetime.now().date(),
            status="Running",
            optimization_strategy=self.strategy
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job
    
    def _load_constraints(self) -> Dict[str, Any]:
        """Load constraints from the database"""
        constraints = {}
        db_constraints = self.db.query(TimetableConstraint).all()
        
        for constraint in db_constraints:
            params = {}
            if constraint.parameters:
                try:
                    params = json.loads(constraint.parameters)
                except json.JSONDecodeError:
                    pass
            
            constraints[constraint.constraint_type] = {
                "name": constraint.name,
                "is_hard": constraint.is_hard_constraint,
                "weight": constraint.weight,
                "params": params
            }
        
        return constraints
    
    def _get_courses_to_schedule(self) -> List[Course]:
        """Get courses to be scheduled for the specified semester"""
        query = self.db.query(Course).filter(Course.semester_id == self.semester_id)
        
        if self.programme_ids:
            query = query.filter(Course.programme_id.in_(self.programme_ids))
        
        if self.department_ids:
            query = query.join(Course.programme).filter(Course.programme.department_id.in_(self.department_ids))
        
        return query.all()
    
    def _get_instructors(self) -> List[Instructor]:
        """Get all available instructors"""
        query = self.db.query(Instructor)
        
        if self.department_ids:
            query = query.filter(Instructor.department_id.in_(self.department_ids))
        
        return query.all()
    
    def _get_instructor_availability(self, instructor_id: int) -> Dict[str, List[Tuple[datetime.time, datetime.time]]]:
        """Get instructor availability for each day"""
        availabilities = self.db.query(InstructorAvailability).filter(
            InstructorAvailability.instructor_id == instructor_id,
            InstructorAvailability.is_available == True
        ).all()
        
        result = {day: [] for day in DEFAULT_TEACHING_HOURS.keys()}
        
        for avail in availabilities:
            result[avail.day].append((avail.start_time, avail.end_time))
        
        # If no specific availability is set, use default teaching hours
        for day, slots in result.items():
            if not slots and day in DEFAULT_TEACHING_HOURS:
                day_hours = DEFAULT_TEACHING_HOURS[day]
                if day_hours["start"] != "00:00" or day_hours["end"] != "00:00":
                    result[day].append((
                        parse_time(day_hours["start"]),
                        parse_time(day_hours["end"])
                    ))
        
        return result
    
    def _get_instructor_preferences(self, instructor_id: int) -> Dict[int, int]:
        """Get instructor preferences for courses (course_id -> preference_level)"""
        preferences = self.db.query(InstructorPreference).filter(
            InstructorPreference.instructor_id == instructor_id
        ).all()
        
        return {pref.course_id: pref.preference_level for pref in preferences}
    
    def _get_existing_timetable_entries(self) -> Dict[str, List[Timetable]]:
        """Get existing timetable entries by day"""
        entries = self.db.query(Timetable).filter(
            Timetable.semester_id == self.semester_id
        ).all()
        
        result = {}
        for entry in entries:
            if entry.day not in result:
                result[entry.day] = []
            result[entry.day].append(entry)
        
        return result
    
    def _get_suitable_rooms(self, course: Course) -> List[Room]:
        """Get suitable rooms for a course based on type and capacity"""
        query = self.db.query(Room)
        
        # Match room type to course type
        if course.type == "Theory":
            query = query.filter(Room.type == "Lecture Hall")
        elif course.type == "Lab":
            query = query.filter(Room.type == "Lab")
        
        # Filter by capacity if course has expected students
        if course.expected_students:
            query = query.filter(Room.capacity >= course.expected_students)
        
        # Order by minimizing wasted capacity
        if course.expected_students:
            return query.order_by(func.abs(Room.capacity - course.expected_students)).all()
        else:
            return query.order_by(Room.capacity).all()
    
    def _get_suitable_instructors(self, course: Course) -> List[Tuple[Instructor, int]]:
        """Get suitable instructors for a course with preference scores"""
        instructors = self._get_instructors()
        result = []
        
        for instructor in instructors:
            # Get instructor's preferences
            preferences = self._get_instructor_preferences(instructor.id)
            
            # Calculate preference score (default to 3 out of 5 if not specified)
            preference_score = preferences.get(course.id, 3)
            
            # Add to result
            result.append((instructor, preference_score))
        
        # Sort by preference score (highest first)
        return sorted(result, key=lambda x: x[1], reverse=True)
    
    def _get_room_bookings(self, room_id: int, day: str) -> List[Tuple[datetime.time, datetime.time]]:
        """Get existing bookings for a room on a specific day"""
        bookings = self.db.query(Timetable).filter(
            Timetable.room_id == room_id,
            Timetable.day == day,
            Timetable.semester_id == self.semester_id
        ).all()
        
        return [(booking.start_time, booking.end_time) for booking in bookings]
    
    def _get_instructor_bookings(self, instructor_id: int, day: str) -> List[Tuple[datetime.time, datetime.time]]:
        """Get existing bookings for an instructor on a specific day"""
        bookings = self.db.query(Timetable).filter(
            Timetable.instructor_id == instructor_id,
            Timetable.day == day,
            Timetable.semester_id == self.semester_id
        ).all()
        
        return [(booking.start_time, booking.end_time) for booking in bookings]
    
    def _calculate_instructor_hours(self, instructor_id: int) -> int:
        """Calculate total teaching hours for an instructor in this semester"""
        bookings = self.db.query(Timetable).filter(
            Timetable.instructor_id == instructor_id,
            Timetable.semester_id == self.semester_id
        ).all()
        
        total_minutes = 0
        for booking in bookings:
            start_minutes = time_to_minutes(booking.start_time)
            end_minutes = time_to_minutes(booking.end_time)
            total_minutes += (end_minutes - start_minutes)
        
        return total_minutes // 60  # Convert to hours
    
    def _find_time_slot(self, course: Course, instructor: Instructor, room: Room) -> Optional[Dict[str, Any]]:
        """
        Find a suitable time slot for a course with a specific instructor and room
        Returns a dict with day, start_time, end_time if found, None otherwise
        """
        # Determine session duration based on course type
        duration_minutes = DEFAULT_LAB_DURATION if course.type == "Lab" else DEFAULT_LECTURE_DURATION
        
        # Get instructor availability
        instructor_availability = self._get_instructor_availability(instructor.id)
        
        # Shuffle days to distribute classes more evenly
        days = list(DEFAULT_TEACHING_HOURS.keys())
        random.shuffle(days)
        
        for day in days:
            # Skip days with no teaching hours
            if day not in DEFAULT_TEACHING_HOURS or DEFAULT_TEACHING_HOURS[day]["start"] == "00:00":
                continue
            
            # Get instructor bookings for this day
            instructor_bookings = self._get_instructor_bookings(instructor.id, day)
            
            # Get room bookings for this day
            room_bookings = self._get_room_bookings(room.id, day)
            
            # Get default day start and end times
            day_start = parse_time(DEFAULT_TEACHING_HOURS[day]["start"])
            day_end = parse_time(DEFAULT_TEACHING_HOURS[day]["end"])
            
            # Find available slots considering both instructor and room availability
            instructor_slots = []
            for avail_start, avail_end in instructor_availability.get(day, []):
                # Get available slots within instructor's availability
                instructor_slots.extend(
                    get_available_time_slots(
                        day, duration_minutes, instructor_bookings,
                        max(avail_start, day_start), min(avail_end, day_end)
                    )
                )
            
            # Find slots that work for both instructor and room
            for start_time, end_time in instructor_slots:
                slot_works_for_room = True
                for room_start, room_end in room_bookings:
                    if check_time_overlap(start_time, end_time, room_start, room_end):
                        slot_works_for_room = False
                        break
                
                if slot_works_for_room:
                    return {
                        "day": day,
                        "start_time": start_time,
                        "end_time": end_time
                    }
        
        # No suitable slot found
        return None
    
    def _check_constraints(self, course: Course, instructor: Instructor, 
                          room: Room, time_slot: Dict[str, Any]) -> List[str]:
        """Check if all constraints are satisfied, return list of violated constraints"""
        violated_constraints = []
        
        # 1. Check room type matches course type
        if (course.type == "Lab" and room.type != "Lab") or \
           (course.type == "Theory" and room.type == "Lab"):
            violated_constraints.append("RoomTypeMatch")
        
        # 2. Check room capacity is sufficient
        if course.expected_students and room.capacity < course.expected_students:
            violated_constraints.append("RoomCapacity")
        
        # 3. Check instructor maximum hours not exceeded
        instructor_hours = self._calculate_instructor_hours(instructor.id)
        duration_hours = (DEFAULT_LAB_DURATION if course.type == "Lab" else DEFAULT_LECTURE_DURATION) // 60
        if (instructor_hours + duration_hours) > instructor.max_hours_per_week:
            violated_constraints.append("InstructorMaxHours")
        
        # 4. Check no room conflicts
        room_bookings = self._get_room_bookings(room.id, time_slot["day"])
        for start, end in room_bookings:
            if check_time_overlap(time_slot["start_time"], time_slot["end_time"], start, end):
                violated_constraints.append("NoRoomConflict")
                break
        
        # 5. Check no instructor conflicts
        instructor_bookings = self._get_instructor_bookings(instructor.id, time_slot["day"])
        for start, end in instructor_bookings:
            if check_time_overlap(time_slot["start_time"], time_slot["end_time"], start, end):
                violated_constraints.append("NoInstructorConflict")
                break
        
        return violated_constraints
    
    def _create_timetable_entry(self, course: Course, instructor: Instructor, 
                              room: Room, time_slot: Dict[str, Any]) -> Optional[Timetable]:
        """Create a new timetable entry"""
        # Check constraints
        violated_constraints = self._check_constraints(course, instructor, room, time_slot)
        
        # Check if any hard constraints are violated
        for constraint in violated_constraints:
            if constraint in self.constraints and self.constraints[constraint]["is_hard"]:
                # Record conflict
                self.conflicts.append(ConflictInfo(
                    conflict_type=constraint,
                    entity_type="Course",
                    entity_id=course.id,
                    entity_name=course.name,
                    time_slot=TimeSlot(
                        day=time_slot["day"],
                        start_time=time_slot["start_time"],
                        end_time=time_slot["end_time"]
                    ),
                    details=f"Cannot schedule {course.name} due to {constraint} constraint"
                ))
                return None
        
        # Create new entry
        entry = Timetable(
            course_id=course.id,
            instructor_id=instructor.id,
            room_id=room.id,
            day=time_slot["day"],
            start_time=time_slot["start_time"],
            end_time=time_slot["end_time"],
            semester_id=self.semester_id
        )
        
        self.db.add(entry)
        self.db.commit()
        self.db.refresh(entry)
        self.entries_created += 1
        
        return entry
    
    def _optimize_timetable(self) -> None:
        """Optimize timetable using constraint satisfaction"""
        # Clear existing entries if requested
        if self.clear_existing:
            self.db.query(Timetable).filter(Timetable.semester_id == self.semester_id).delete()
            self.db.commit()
        
        # Get courses to schedule
        courses = self._get_courses_to_schedule()
        
        # Sort courses by priority based on strategy
        if self.strategy == OptimizationStrategyEnum.rooms:
            # Prioritize courses with specific room requirements
            courses.sort(key=lambda c: 1 if c.type == "Lab" else 0, reverse=True)
        elif self.strategy == OptimizationStrategyEnum.instructors:
            # Prioritize courses with fewer suitable instructors
            pass
        elif self.strategy == OptimizationStrategyEnum.students:
            # Prioritize courses with more students
            courses.sort(key=lambda c: c.expected_students or 0, reverse=True)
        else:  # balanced
            # Use a balanced approach, prioritize constrained courses
            random.shuffle(courses)
        
        # Start timer
        start_time = time.time()
        iteration = 0
        
        # Schedule each course
        for course in courses:
            # Check if we've exceeded time limit or iterations
            if (time.time() - start_time) > self.time_limit_seconds or iteration >= self.max_iterations:
                break
            
            iteration += 1
            
            # Skip courses that already have an entry and we're respecting existing entries
            if self.respect_existing and not self.clear_existing:
                existing = self.db.query(Timetable).filter(
                    Timetable.course_id == course.id,
                    Timetable.semester_id == self.semester_id
                ).first()
                
                if existing:
                    continue
            
            # Get suitable rooms for this course
            rooms = self._get_suitable_rooms(course)
            if not rooms:
                self.conflicts.append(ConflictInfo(
                    conflict_type="NoSuitableRoom",
                    entity_type="Course",
                    entity_id=course.id,
                    entity_name=course.name,
                    time_slot=TimeSlot(
                        day="",
                        start_time=datetime.time(0, 0),
                        end_time=datetime.time(0, 0)
                    ),
                    details=f"No suitable room found for {course.name}"
                ))
                continue
            
            # Get suitable instructors for this course
            instructors_with_scores = self._get_suitable_instructors(course)
            if not instructors_with_scores:
                self.conflicts.append(ConflictInfo(
                    conflict_type="NoSuitableInstructor",
                    entity_type="Course",
                    entity_id=course.id,
                    entity_name=course.name,
                    time_slot=TimeSlot(
                        day="",
                        start_time=datetime.time(0, 0),
                        end_time=datetime.time(0, 0)
                    ),
                    details=f"No suitable instructor found for {course.name}"
                ))
                continue
            
            # Try each instructor and room combination until we find a suitable slot
            scheduled = False
            for instructor, score in instructors_with_scores:
                for room in rooms:
                    # Find a suitable time slot
                    time_slot = self._find_time_slot(course, instructor, room)
                    if time_slot:
                        # Create timetable entry
                        entry = self._create_timetable_entry(course, instructor, room, time_slot)
                        if entry:
                            scheduled = True
                            break
                
                if scheduled:
                    break
            
            # Record if we couldn't schedule the course
            if not scheduled:
                self.conflicts.append(ConflictInfo(
                    conflict_type="NoSuitableTimeSlot",
                    entity_type="Course",
                    entity_id=course.id,
                    entity_name=course.name,
                    time_slot=TimeSlot(
                        day="",
                        start_time=datetime.time(0, 0),
                        end_time=datetime.time(0, 0)
                    ),
                    details=f"Could not find a suitable time slot for {course.name}"
                ))
    
    def _calculate_statistics(self) -> TimetableStatistics:
        """Calculate statistics about the generated timetable"""
        # Get all timetable entries for the semester
        entries = self.db.query(Timetable).filter(Timetable.semester_id == self.semester_id).all()
        
        # Get counts
        total_courses = self.db.query(Course).filter(Course.semester_id == self.semester_id).count()
        courses_scheduled = len({entry.course_id for entry in entries})
        unique_instructors = len({entry.instructor_id for entry in entries})
        unique_rooms = len({entry.room_id for entry in entries})
        
        # Calculate total hours scheduled
        total_minutes = sum([
            time_to_minutes(entry.end_time) - time_to_minutes(entry.start_time)
            for entry in entries
        ])
        total_hours = total_minutes / 60
        
        # Calculate instructor utilization
        all_instructors = self._get_instructors()
        instructor_hours = {}
        for instructor in all_instructors:
            instructor_hours[instructor.id] = self._calculate_instructor_hours(instructor.id)
        
        avg_instructor_utilization = sum(instructor_hours.values()) / (len(instructor_hours) * 40) * 100 if instructor_hours else 0
        
        # Calculate room utilization - rough estimate based on total teaching hours / total available hours
        all_rooms = self.db.query(Room).all()
        available_room_hours = len(all_rooms) * 45  # Assuming ~45 teaching hours per week per room
        room_utilization = total_hours / available_room_hours * 100 if available_room_hours > 0 else 0
        
        # Calculate percentage of courses scheduled with preferred instructors and suitable rooms
        # This would require more complex analysis of preferences and room suitability
        
        return TimetableStatistics(
            total_courses=total_courses,
            total_instructors=unique_instructors,
            total_rooms=unique_rooms,
            total_hours_scheduled=int(total_hours),
            room_utilization_percentage=min(100, room_utilization),
            instructor_utilization_percentage=min(100, avg_instructor_utilization),
            courses_with_preferred_instructors_percentage=min(100, courses_scheduled / total_courses * 100) if total_courses > 0 else 0,
            courses_in_suitable_rooms_percentage=min(100, courses_scheduled / total_courses * 100) if total_courses > 0 else 0
        )
    
    def generate(self) -> TimetableGenerationResult:
        """Generate the timetable and return results"""
        try:
            # Start timer
            start_time = time.time()
            
            # Run optimization
            self._optimize_timetable()
            
            # Calculate execution time
            execution_time = time.time() - start_time
            
            # Calculate statistics
            statistics = self._calculate_statistics()
            
            # Update job record
            self.job.completed_at = datetime.now().date()
            self.job.status = "Completed"
            self.job.result_metrics = json.dumps({
                "entries_created": self.entries_created,
                "conflicts": len(self.conflicts),
                "execution_time": execution_time,
                "statistics": statistics.dict()
            })
            self.db.commit()
            
            # Return result
            return TimetableGenerationResult(
                job_id=self.job.id,
                status="Completed",
                entries_created=self.entries_created,
                conflicts_detected=self.conflicts,
                statistics=statistics,
                execution_time_seconds=execution_time
            )
            
        except Exception as e:
            # Handle errors
            self.job.status = "Failed"
            self.job.error_message = str(e)
            self.db.commit()
            
            # Re-raise for the API to handle
            raise

def generate_timetable(
    db: Session,
    semester_id: int,
    strategy: OptimizationStrategyEnum = OptimizationStrategyEnum.balanced,
    department_ids: List[int] = None,
    programme_ids: List[int] = None,
    respect_existing: bool = True,
    clear_existing: bool = False,
    max_iterations: int = 1000,
    time_limit_seconds: int = 300
) -> TimetableGenerationResult:
    """
    Generate timetable for a semester
    
    Args:
        db: Database session
        semester_id: ID of the semester to generate timetable for
        strategy: Optimization strategy
        department_ids: List of department IDs to include (None for all)
        programme_ids: List of programme IDs to include (None for all)
        respect_existing: Whether to keep existing timetable entries
        clear_existing: Whether to clear existing timetable entries
        max_iterations: Maximum number of iterations
        time_limit_seconds: Time limit in seconds
        
    Returns:
        TimetableGenerationResult with statistics and conflicts
    """
    generator = TimetableGenerator(
        db=db,
        semester_id=semester_id,
        strategy=strategy,
        department_ids=department_ids,
        programme_ids=programme_ids,
        respect_existing=respect_existing,
        clear_existing=clear_existing,
        max_iterations=max_iterations,
        time_limit_seconds=time_limit_seconds
    )
    
    return generator.generate()