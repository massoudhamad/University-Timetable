from pydantic import BaseModel, Field, EmailStr, validator, root_validator
from typing import Optional, List, Dict, Any, Union
from datetime import date, time, datetime
from enum import Enum

# Enum classes for validation
class StatusEnum(str, Enum):
    active = "Active"
    not_active = "Not Active"

class CourseTypeEnum(str, Enum):
    theory = "Theory"
    lab = "Lab"

class RoleEnum(str, Enum):
    admin = "Admin"
    faculty = "Faculty"
    student = "Student"

class RoomTypeEnum(str, Enum):
    lecture_hall = "Lecture Hall"
    lab = "Lab"

class DayEnum(str, Enum):
    monday = "Monday"
    tuesday = "Tuesday"
    wednesday = "Wednesday"
    thursday = "Thursday"
    friday = "Friday"
    saturday = "Saturday"
    sunday = "Sunday"

class JobStatusEnum(str, Enum):
    pending = "Pending"
    running = "Running"
    completed = "Completed"
    failed = "Failed"

class ConstraintTypeEnum(str, Enum):
    no_room_conflict = "NoRoomConflict"
    no_instructor_conflict = "NoInstructorConflict"
    room_type_match = "RoomTypeMatch"
    instructor_availability = "InstructorAvailability"
    instructor_max_hours = "InstructorMaxHours"
    consecutive_courses = "ConsecutiveCourses"
    minimize_gaps = "MinimizeGaps"
    preferred_time_slots = "PreferredTimeSlots"
    balanced_distribution = "BalancedDistribution"

class OptimizationStrategyEnum(str, Enum):
    balanced = "balanced"
    rooms = "rooms"
    instructors = "instructors"
    students = "students"
    minimal_changes = "minimal_changes"

# Base schemas
class AcademicYearBase(BaseModel):
    year: str
    status: StatusEnum

class SemesterBase(BaseModel):
    name: str
    start_date: date
    end_date: date
    academic_year_id: int

class DepartmentBase(BaseModel):
    name: str

class ProgrammeBase(BaseModel):
    name: str
    department_id: int

class CourseBase(BaseModel):
    code: str
    name: str
    type: CourseTypeEnum
    programme_id: int
    semester_id: int
    credit_hours: int = 3
    expected_students: Optional[int] = None

class UserBase(BaseModel):
    name: str
    email: EmailStr
    role: RoleEnum

class InstructorBase(BaseModel):
    user_id: int
    department_id: int
    max_hours_per_week: int = 20

class RoomBase(BaseModel):
    name: str
    capacity: int
    type: RoomTypeEnum

class TimetableBase(BaseModel):
    course_id: int
    instructor_id: int
    room_id: int
    day: DayEnum
    start_time: time
    end_time: time
    semester_id: int

class InstructorAvailabilityBase(BaseModel):
    instructor_id: int
    day: DayEnum
    start_time: time
    end_time: time
    is_available: bool = True

class InstructorPreferenceBase(BaseModel):
    instructor_id: int
    course_id: int
    preference_level: int = Field(..., ge=1, le=5)

class TimetableConstraintBase(BaseModel):
    name: str
    constraint_type: ConstraintTypeEnum
    is_hard_constraint: bool = True
    weight: int = 1
    parameters: Optional[Dict[str, Any]] = None

class TimetableGenerationJobBase(BaseModel):
    semester_id: int
    optimization_strategy: OptimizationStrategyEnum = OptimizationStrategyEnum.balanced

# Create schemas (for POST requests)
class AcademicYearCreate(AcademicYearBase):
    pass

class SemesterCreate(SemesterBase):
    @validator('end_date')
    def end_date_must_be_after_start_date(cls, v, values):
        if 'start_date' in values and v <= values['start_date']:
            raise ValueError('end_date must be after start_date')
        return v

class DepartmentCreate(DepartmentBase):
    pass

class ProgrammeCreate(ProgrammeBase):
    pass

class CourseCreate(CourseBase):
    pass

class UserCreate(UserBase):
    password: str
    
    @validator('password')
    def password_min_length(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v

class InstructorCreate(InstructorBase):
    pass

class RoomCreate(RoomBase):
    @validator('capacity')
    def capacity_must_be_positive(cls, v):
        if v <= 0:
            raise ValueError('Capacity must be positive')
        return v

class TimetableCreate(TimetableBase):
    @validator('end_time')
    def end_time_must_be_after_start_time(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('end_time must be after start_time')
        return v

class InstructorAvailabilityCreate(InstructorAvailabilityBase):
    @validator('end_time')
    def end_time_must_be_after_start_time(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('end_time must be after start_time')
        return v

class InstructorPreferenceCreate(InstructorPreferenceBase):
    pass

class TimetableConstraintCreate(TimetableConstraintBase):
    pass

class TimetableGenerationJobCreate(TimetableGenerationJobBase):
    pass

# Update schemas (for PUT/PATCH requests)
class AcademicYearUpdate(BaseModel):
    year: Optional[str] = None
    status: Optional[StatusEnum] = None

class SemesterUpdate(BaseModel):
    name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    academic_year_id: Optional[int] = None

class DepartmentUpdate(BaseModel):
    name: Optional[str] = None

class ProgrammeUpdate(BaseModel):
    name: Optional[str] = None
    department_id: Optional[int] = None

class CourseUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    type: Optional[CourseTypeEnum] = None
    programme_id: Optional[int] = None
    semester_id: Optional[int] = None
    credit_hours: Optional[int] = None
    expected_students: Optional[int] = None

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[RoleEnum] = None
    password: Optional[str] = None

class InstructorUpdate(BaseModel):
    user_id: Optional[int] = None
    department_id: Optional[int] = None
    max_hours_per_week: Optional[int] = None

class RoomUpdate(BaseModel):
    name: Optional[str] = None
    capacity: Optional[int] = None
    type: Optional[RoomTypeEnum] = None

class TimetableUpdate(BaseModel):
    course_id: Optional[int] = None
    instructor_id: Optional[int] = None
    room_id: Optional[int] = None
    day: Optional[DayEnum] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None

class InstructorAvailabilityUpdate(BaseModel):
    day: Optional[DayEnum] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    is_available: Optional[bool] = None

class InstructorPreferenceUpdate(BaseModel):
    preference_level: Optional[int] = Field(None, ge=1, le=5)

class TimetableConstraintUpdate(BaseModel):
    name: Optional[str] = None
    constraint_type: Optional[ConstraintTypeEnum] = None
    is_hard_constraint: Optional[bool] = None
    weight: Optional[int] = None
    parameters: Optional[Dict[str, Any]] = None

# Response schemas (for GET responses)
class AcademicYearResponse(AcademicYearBase):
    id: int
    
    class Config:
        orm_mode = True

class SemesterResponse(SemesterBase):
    id: int
    
    class Config:
        orm_mode = True

class DepartmentResponse(DepartmentBase):
    id: int
    
    class Config:
        orm_mode = True

class ProgrammeResponse(ProgrammeBase):
    id: int
    
    class Config:
        orm_mode = True

class CourseResponse(CourseBase):
    id: int
    
    class Config:
        orm_mode = True

class UserResponse(UserBase):
    id: int
    
    class Config:
        orm_mode = True

class InstructorResponse(InstructorBase):
    id: int
    
    class Config:
        orm_mode = True

class RoomResponse(RoomBase):
    id: int
    
    class Config:
        orm_mode = True

class TimetableResponse(TimetableBase):
    id: int
    
    class Config:
        orm_mode = True

class InstructorAvailabilityResponse(InstructorAvailabilityBase):
    id: int
    
    class Config:
        orm_mode = True

class InstructorPreferenceResponse(InstructorPreferenceBase):
    id: int
    
    class Config:
        orm_mode = True

class TimetableConstraintResponse(TimetableConstraintBase):
    id: int
    
    class Config:
        orm_mode = True

class TimetableGenerationJobResponse(TimetableGenerationJobBase):
    id: int
    created_at: date
    completed_at: Optional[date] = None
    status: JobStatusEnum
    error_message: Optional[str] = None
    result_metrics: Optional[Dict[str, Any]] = None
    
    class Config:
        orm_mode = True

# Specialized schemas for timetable generation
class TimetableGenerationRequest(BaseModel):
    semester_id: int
    department_ids: Optional[List[int]] = None
    programme_ids: Optional[List[int]] = None
    strategy: OptimizationStrategyEnum = OptimizationStrategyEnum.balanced
    respect_existing: bool = True
    clear_existing: bool = False
    max_iterations: Optional[int] = None
    time_limit_seconds: Optional[int] = None

class TimeSlot(BaseModel):
    day: DayEnum
    start_time: time
    end_time: time

class ConflictInfo(BaseModel):
    conflict_type: str
    entity_type: str
    entity_id: int
    entity_name: str
    time_slot: TimeSlot
    details: str

class TimetableStatistics(BaseModel):
    total_courses: int
    total_instructors: int
    total_rooms: int
    total_hours_scheduled: int
    room_utilization_percentage: float
    instructor_utilization_percentage: float
    courses_with_preferred_instructors_percentage: float
    courses_in_suitable_rooms_percentage: float

class TimetableGenerationResult(BaseModel):
    job_id: int
    status: JobStatusEnum
    entries_created: int
    conflicts_detected: List[ConflictInfo] = []
    statistics: Optional[TimetableStatistics] = None
    execution_time_seconds: float

# Authentication schemas
class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = None

# Search parameters
class TimetableSearchParams(BaseModel):
    semester_id: Optional[int] = None
    department_id: Optional[int] = None
    programme_id: Optional[int] = None
    course_id: Optional[int] = None
    instructor_id: Optional[int] = None
    room_id: Optional[int] = None
    day: Optional[DayEnum] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None