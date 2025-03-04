from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from typing import List, Dict, Any, Optional
from datetime import date, time, datetime

from app.database import get_db
from app.models import (
    Course, Instructor, Room, Timetable, Semester, TimetableGenerationJob,
    InstructorAvailability, InstructorPreference, TimetableConstraint
)
from app.schemas import (
    TimetableCreate, TimetableResponse, TimetableUpdate,
    TimetableGenerationRequest, TimetableGenerationResult, TimetableSearchParams,
    InstructorAvailabilityCreate, InstructorAvailabilityResponse,
    InstructorPreferenceCreate, InstructorPreferenceResponse,
    TimetableConstraintCreate, TimetableConstraintResponse,
    TimetableStatistics, DayEnum
)
from app.auth import get_current_user, get_admin_user, get_faculty_or_admin_user
from app.timetable_generator import generate_timetable

router = APIRouter(prefix="/timetable", tags=["Timetable"])

# -------------------- TIMETABLE ENTRIES --------------------
@router.post("/", response_model=TimetableResponse, status_code=status.HTTP_201_CREATED)
def create_timetable_entry(
    entry: TimetableCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_faculty_or_admin_user)
):
    """Create a single timetable entry"""
    # Validate resources exist
    course = db.query(Course).filter(Course.id == entry.course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    instructor = db.query(Instructor).filter(Instructor.id == entry.instructor_id).first()
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor not found")
    
    room = db.query(Room).filter(Room.id == entry.room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    semester = db.query(Semester).filter(Semester.id == entry.semester_id).first()
    if not semester:
        raise HTTPException(status_code=404, detail="Semester not found")
    
    # Check for time conflicts (room)
    room_conflict = db.query(Timetable).filter(
        Timetable.room_id == entry.room_id,
        Timetable.day == entry.day,
        Timetable.semester_id == entry.semester_id,
        or_(
            and_(Timetable.start_time <= entry.start_time, Timetable.end_time > entry.start_time),
            and_(Timetable.start_time < entry.end_time, Timetable.end_time >= entry.end_time),
            and_(Timetable.start_time >= entry.start_time, Timetable.end_time <= entry.end_time)
        )
    ).first()
    
    if room_conflict:
        raise HTTPException(
            status_code=400, 
            detail=f"Room conflict detected for {room.name} on {entry.day} at time {entry.start_time}-{entry.end_time}"
        )
    
    # Check for time conflicts (instructor)
    instructor_conflict = db.query(Timetable).filter(
        Timetable.instructor_id == entry.instructor_id,
        Timetable.day == entry.day,
        Timetable.semester_id == entry.semester_id,
        or_(
            and_(Timetable.start_time <= entry.start_time, Timetable.end_time > entry.start_time),
            and_(Timetable.start_time < entry.end_time, Timetable.end_time >= entry.end_time),
            and_(Timetable.start_time >= entry.start_time, Timetable.end_time <= entry.end_time)
        )
    ).first()
    
    if instructor_conflict:
        raise HTTPException(
            status_code=400, 
            detail=f"Instructor conflict detected on {entry.day} at time {entry.start_time}-{entry.end_time}"
        )
    
    # Validate room type matches course type
    if (course.type == "Lab" and room.type != "Lab") or \
       (course.type == "Theory" and room.type == "Lab" and room.type != "Lecture Hall"):
        raise HTTPException(
            status_code=400,
            detail=f"Room type ({room.type}) does not match course type ({course.type})"
        )
    
    # Create new entry
    db_entry = Timetable(**entry.dict())
    db.add(db_entry)
    db.commit()
    db.refresh(db_entry)
    return db_entry

@router.get("/", response_model=List[TimetableResponse])
def get_timetable_entries(
    params: TimetableSearchParams = Depends(),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get timetable entries with optional filtering"""
    query = db.query(Timetable)
    
    # Apply filters
    if params.semester_id:
        query = query.filter(Timetable.semester_id == params.semester_id)
    
    if params.course_id:
        query = query.filter(Timetable.course_id == params.course_id)
    
    if params.instructor_id:
        query = query.filter(Timetable.instructor_id == params.instructor_id)
    
    if params.room_id:
        query = query.filter(Timetable.room_id == params.room_id)
    
    if params.day:
        query = query.filter(Timetable.day == params.day)
    
    if params.start_time:
        query = query.filter(Timetable.start_time >= params.start_time)
    
    if params.end_time:
        query = query.filter(Timetable.end_time <= params.end_time)
    
    if params.programme_id:
        query = query.join(Course).filter(Course.programme_id == params.programme_id)
    
    if params.department_id:
        query = query.join(Instructor).filter(Instructor.department_id == params.department_id)
    
    entries = query.offset(skip).limit(limit).all()
    return entries

@router.get("/{entry_id}", response_model=TimetableResponse)
def get_timetable_entry(
    entry_id: int,
    db: Session = Depends(get_db)
):
    """Get a single timetable entry by ID"""
    entry = db.query(Timetable).filter(Timetable.id == entry_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Timetable entry not found")
    return entry

@router.put("/{entry_id}", response_model=TimetableResponse)
def update_timetable_entry(
    entry_id: int,
    entry: TimetableUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_faculty_or_admin_user)
):
    """Update a timetable entry"""
    db_entry = db.query(Timetable).filter(Timetable.id == entry_id).first()
    if not db_entry:
        raise HTTPException(status_code=404, detail="Timetable entry not found")
    
    update_data = entry.dict(exclude_unset=True)
    
    # If updating time or room or instructor, check for conflicts
    if any(field in update_data for field in ["day", "start_time", "end_time", "room_id", "instructor_id"]):
        # Get updated values
        new_day = update_data.get("day", db_entry.day)
        new_start_time = update_data.get("start_time", db_entry.start_time)
        new_end_time = update_data.get("end_time", db_entry.end_time)
        new_room_id = update_data.get("room_id", db_entry.room_id)
        new_instructor_id = update_data.get("instructor_id", db_entry.instructor_id)
        
        # Check room conflict if room or time is changing
        if "room_id" in update_data or "day" in update_data or "start_time" in update_data or "end_time" in update_data:
            room_conflict = db.query(Timetable).filter(
                Timetable.room_id == new_room_id,
                Timetable.day == new_day,
                Timetable.id != entry_id,
                or_(
                    and_(Timetable.start_time <= new_start_time, Timetable.end_time > new_start_time),
                    and_(Timetable.start_time < new_end_time, Timetable.end_time >= new_end_time),
                    and_(Timetable.start_time >= new_start_time, Timetable.end_time <= new_end_time)
                )
            ).first()
            
            if room_conflict:
                room = db.query(Room).filter(Room.id == new_room_id).first()
                raise HTTPException(
                    status_code=400, 
                    detail=f"Room conflict detected for {room.name if room else 'room'} on {new_day} at time {new_start_time}-{new_end_time}"
                )
        
        # Check instructor conflict if instructor or time is changing
        if "instructor_id" in update_data or "day" in update_data or "start_time" in update_data or "end_time" in update_data:
            instructor_conflict = db.query(Timetable).filter(
                Timetable.instructor_id == new_instructor_id,
                Timetable.day == new_day,
                Timetable.id != entry_id,
                or_(
                    and_(Timetable.start_time <= new_start_time, Timetable.end_time > new_start_time),
                    and_(Timetable.start_time < new_end_time, Timetable.end_time >= new_end_time),
                    and_(Timetable.start_time >= new_start_time, Timetable.end_time <= new_end_time)
                )
            ).first()
            
            if instructor_conflict:
                instructor = db.query(Instructor).filter(Instructor.id == new_instructor_id).first()
                raise HTTPException(
                    status_code=400, 
                    detail=f"Instructor conflict detected on {new_day} at time {new_start_time}-{new_end_time}"
                )
        
        # Validate room type if changing room or course
        if "room_id" in update_data or "course_id" in update_data:
            course_id = update_data.get("course_id", db_entry.course_id)
            room_id = update_data.get("room_id", db_entry.room_id)
            
            course = db.query(Course).filter(Course.id == course_id).first()
            room = db.query(Room).filter(Room.id == room_id).first()
            
            if course and room and ((course.type == "Lab" and room.type != "Lab") or \
                                    (course.type == "Theory" and room.type == "Lab")):
                raise HTTPException(
                    status_code=400,
                    detail=f"Room type ({room.type}) does not match course type ({course.type})"
                )
    
    # Update entry
    for key, value in update_data.items():
        setattr(db_entry, key, value)
    
    db.commit()
    db.refresh(db_entry)
    return db_entry

@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_timetable_entry(
    entry_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_faculty_or_admin_user)
):
    """Delete a timetable entry"""
    db_entry = db.query(Timetable).filter(Timetable.id == entry_id).first()
    if not db_entry:
        raise HTTPException(status_code=404, detail="Timetable entry not found")
    
    db.delete(db_entry)
    db.commit()
    return None

# -------------------- TIMETABLE GENERATION --------------------
def _run_timetable_generation_background(
    db: Session,
    request: TimetableGenerationRequest
):
    """Run timetable generation in background"""
    # Create a new session for background task
    db_session = SessionLocal()
    try:
        # Generate timetable
        generate_timetable(
            db=db_session,
            semester_id=request.semester_id,
            strategy=request.strategy,
            department_ids=request.department_ids,
            programme_ids=request.programme_ids,
            respect_existing=request.respect_existing,
            clear_existing=request.clear_existing,
            max_iterations=request.max_iterations or 1000,
            time_limit_seconds=request.time_limit_seconds or 300
        )
    finally:
        db_session.close()

@router.post("/generate", response_model=Dict[str, Any])
def generate_timetable_request(
    request: TimetableGenerationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Start timetable generation process"""
    # Validate semester exists
    semester = db.query(Semester).filter(Semester.id == request.semester_id).first()
    if not semester:
        raise HTTPException(status_code=404, detail="Semester not found")
    
    # Create job record
    job = TimetableGenerationJob(
        semester_id=request.semester_id,
        created_at=datetime.now().date(),
        status="Pending",
        optimization_strategy=request.strategy
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    # Start background task
    background_tasks.add_task(
        _run_timetable_generation_background,
        db,
        request
    )
    
    return {
        "message": "Timetable generation started",
        "job_id": job.id
    }

@router.get("/generate/{job_id}", response_model=TimetableGenerationResult)
def get_timetable_generation_status(
    job_id: int,
    db: Session = Depends(get_db)
):
    """Get status of a timetable generation job"""
    job = db.query(TimetableGenerationJob).filter(TimetableGenerationJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Timetable generation job not found")
    
    # Parse result metrics if completed
    statistics = None
    conflicts = []
    entries_created = 0
    execution_time = 0
    
    if job.result_metrics:
        try:
            metrics = json.loads(job.result_metrics)
            entries_created = metrics.get("entries_created", 0)
            conflicts = metrics.get("conflicts", [])
            execution_time = metrics.get("execution_time", 0)
            
            if "statistics" in metrics:
                statistics = TimetableStatistics(**metrics["statistics"])
        except json.JSONDecodeError:
            pass
    
    return TimetableGenerationResult(
        job_id=job.id,
        status=job.status,
        entries_created=entries_created,
        conflicts_detected=conflicts,
        statistics=statistics,
        execution_time_seconds=execution_time
    )

# -------------------- INSTRUCTOR AVAILABILITY --------------------
@router.post("/instructor-availability", response_model=InstructorAvailabilityResponse, status_code=status.HTTP_201_CREATED)
def create_instructor_availability(
    availability: InstructorAvailabilityCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_faculty_or_admin_user)
):
    """Create instructor availability record"""
    # Validate instructor exists
    instructor = db.query(Instructor).filter(Instructor.id == availability.instructor_id).first()
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor not found")
    
    # Create availability record
    db_availability = InstructorAvailability(**availability.dict())
    db.add(db_availability)
    db.commit()
    db.refresh(db_availability)
    return db_availability

@router.get("/instructor-availability", response_model=List[InstructorAvailabilityResponse])
def get_instructor_availabilities(
    instructor_id: Optional[int] = None,
    day: Optional[DayEnum] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get instructor availability records"""
    query = db.query(InstructorAvailability)
    
    if instructor_id:
        query = query.filter(InstructorAvailability.instructor_id == instructor_id)
    
    if day:
        query = query.filter(InstructorAvailability.day == day)
    
    availabilities = query.offset(skip).limit(limit).all()
    return availabilities

# -------------------- INSTRUCTOR PREFERENCES --------------------
@router.post("/instructor-preference", response_model=InstructorPreferenceResponse, status_code=status.HTTP_201_CREATED)
def create_instructor_preference(
    preference: InstructorPreferenceCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_faculty_or_admin_user)
):
    """Create instructor course preference record"""
    # Validate instructor exists
    instructor = db.query(Instructor).filter(Instructor.id == preference.instructor_id).first()
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor not found")
    
    # Validate course exists
    course = db.query(Course).filter(Course.id == preference.course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Check if preference already exists
    existing = db.query(InstructorPreference).filter(
        InstructorPreference.instructor_id == preference.instructor_id,
        InstructorPreference.course_id == preference.course_id
    ).first()
    
    if existing:
        # Update existing preference
        existing.preference_level = preference.preference_level
        db.commit()
        db.refresh(existing)
        return existing
    
    # Create new preference
    db_preference = InstructorPreference(**preference.dict())
    db.add(db_preference)
    db.commit()
    db.refresh(db_preference)
    return db_preference

@router.get("/instructor-preference", response_model=List[InstructorPreferenceResponse])
def get_instructor_preferences(
    instructor_id: Optional[int] = None,
    course_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get instructor course preferences"""
    query = db.query(InstructorPreference)
    
    if instructor_id:
        query = query.filter(InstructorPreference.instructor_id == instructor_id)
    
    if course_id:
        query = query.filter(InstructorPreference.course_id == course_id)
    
    preferences = query.offset(skip).limit(limit).all()
    return preferences

# -------------------- TIMETABLE CONSTRAINTS --------------------
@router.post("/constraint", response_model=TimetableConstraintResponse, status_code=status.HTTP_201_CREATED)
def create_timetable_constraint(
    constraint: TimetableConstraintCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_admin_user)
):
    """Create timetable constraint"""
    # Convert parameters to JSON string if provided
    parameters = None
    if constraint.parameters:
        parameters = json.dumps(constraint.parameters)
    
    # Create constraint
    db_constraint = TimetableConstraint(
        name=constraint.name,
        constraint_type=constraint.constraint_type,
        is_hard_constraint=constraint.is_hard_constraint,
        weight=constraint.weight,
        parameters=parameters
    )
    db.add(db_constraint)
    db.commit()
    db.refresh(db_constraint)
    
    # Parse parameters for response
    response = TimetableConstraintResponse(
        id=db_constraint.id,
        name=db_constraint.name,
        constraint_type=db_constraint.constraint_type,
        is_hard_constraint=db_constraint.is_hard_constraint,
        weight=db_constraint.weight,
        parameters=constraint.parameters
    )
    
    return response

@router.get("/constraint", response_model=List[TimetableConstraintResponse])
def get_timetable_constraints(
    constraint_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get timetable constraints"""
    query = db.query(TimetableConstraint)
    
    if constraint_type:
        query = query.filter(TimetableConstraint.constraint_type == constraint_type)
    
    constraints = query.offset(skip).limit(limit).all()
    
    # Parse parameters for each constraint
    result = []
    for constraint in constraints:
        parameters = None
        if constraint.parameters:
            try:
                parameters = json.loads(constraint.parameters)
            except json.JSONDecodeError:
                parameters = {}
        
        result.append(TimetableConstraintResponse(
            id=constraint.id,
            name=constraint.name,
            constraint_type=constraint.constraint_type,
            is_hard_constraint=constraint.is_hard_constraint,
            weight=constraint.weight,
            parameters=parameters
        ))
    
    return result

# -------------------- STATISTICS & ANALYSIS --------------------
@router.get("/statistics/{semester_id}", response_model=TimetableStatistics)
def get_timetable_statistics(
    semester_id: int,
    db: Session = Depends(get_db)
):
    """Get statistics for a semester's timetable"""
    # Get all timetable entries for the semester
    entries = db.query(Timetable).filter(Timetable.semester_id == semester_id).all()
    
    # If no entries, return empty statistics
    if not entries:
        return TimetableStatistics(
            total_courses=0,
            total_instructors=0,
            total_rooms=0,
            total_hours_scheduled=0,
            room_utilization_percentage=0,
            instructor_utilization_percentage=0,
            courses_with_preferred_instructors_percentage=0,
            courses_in_suitable_rooms_percentage=0
        )
    
    # Calculate statistics
    # (Similar to the _calculate_statistics method in TimetableGenerator)
    total_courses = db.query(Course).filter(Course.semester_id == semester_id).count()
    courses_scheduled = len({entry.course_id for entry in entries})
    unique_instructors = len({entry.instructor_id for entry in entries})
    unique_rooms = len({entry.room_id for entry in entries})
    
    # Calculate total hours scheduled
    total_minutes = sum([
        (time_to_minutes(entry.end_time) - time_to_minutes(entry.start_time))
        for entry in entries
    ])
    total_hours = total_minutes / 60
    
    # Calculate instructor utilization
    all_instructors = db.query(Instructor).all()
    
    # Calculate room utilization
    all_rooms = db.query(Room).all()
    available_room_hours = len(all_rooms) * 45  # Assuming ~45 teaching hours per week per room
    room_utilization = total_hours / available_room_hours * 100 if available_room_hours > 0 else 0
    
    return TimetableStatistics(
        total_courses=total_courses,
        total_instructors=unique_instructors,
        total_rooms=unique_rooms,
        total_hours_scheduled=int(total_hours),
        room_utilization_percentage=min(100, room_utilization),
        instructor_utilization_percentage=min(100, 75),  # Placeholder
        courses_with_preferred_instructors_percentage=min(100, courses_scheduled / total_courses * 100) if total_courses > 0 else 0,
        courses_in_suitable_rooms_percentage=min(100, courses_scheduled / total_courses * 100) if total_courses > 0 else 0
    )

@router.get("/conflicts/{semester_id}")
def check_timetable_conflicts(
    semester_id: int,
    db: Session = Depends(get_db)
):
    """Check for conflicts in existing timetable"""
    # Get all timetable entries for the semester
    entries = db.query(Timetable).filter(Timetable.semester_id == semester_id).all()
    
    # Group entries by day
    entries_by_day = {}
    for entry in entries:
        if entry.day not in entries_by_day:
            entries_by_day[entry.day] = []
        entries_by_day[entry.day].append(entry)
    
    conflicts = []
    
    # Check for conflicts within each day
    for day, day_entries in entries_by_day.items():
        for i, entry1 in enumerate(day_entries):
            for j in range(i + 1, len(day_entries)):
                entry2 = day_entries[j]
                
                # Check if time periods overlap
                if check_time_overlap(entry1.start_time, entry1.end_time, entry2.start_time, entry2.end_time):
                    # Check for room conflict
                    if entry1.room_id == entry2.room_id:
                        room = db.query(Room).filter(Room.id == entry1.room_id).first()
                        conflicts.append({
                            "conflict_type": "RoomConflict",
                            "entity_type": "Room",
                            "entity_id": entry1.room_id,
                            "entity_name": room.name if room else "Unknown Room",
                            "entries": [entry1.id, entry2.id],
                            "day": day,
                            "time": f"{entry1.start_time}-{entry1.end_time}",
                            "details": f"Room {room.name if room else 'Unknown'} is double-booked"
                        })
                    
                    # Check for instructor conflict
                    if entry1.instructor_id == entry2.instructor_id:
                        instructor = db.query(Instructor).filter(Instructor.id == entry1.instructor_id).first()
                        user = None
                        if instructor:
                            user = db.query(User).filter(User.id == instructor.user_id).first()
                        
                        conflicts.append({
                            "conflict_type": "InstructorConflict",
                            "entity_type": "Instructor",
                            "entity_id": entry1.instructor_id,
                            "entity_name": user.name if user else "Unknown Instructor",
                            "entries": [entry1.id, entry2.id],
                            "day": day,
                            "time": f"{entry1.start_time}-{entry1.end_time}",
                            "details": f"Instructor {user.name if user else 'Unknown'} is double-booked"
                        })
    
    return {
        "semester_id": semester_id,
        "total_entries": len(entries),
        "conflicts_found": len(conflicts),
        "conflicts": conflicts
    }

def time_to_minutes(t: time) -> int:
    """Convert time to minutes from midnight"""
    return t.hour * 60 + t.minute

def check_time_overlap(start1: time, end1: time, start2: time, end2: time) -> bool:
    """Check if two time periods overlap"""
    return max(time_to_minutes(start1), time_to_minutes(start2)) < min(time_to_minutes(end1), time_to_minutes(end2))

# Import SessionLocal for background tasks
from app.database import SessionLocal
import json