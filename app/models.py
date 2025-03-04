from sqlalchemy import Column, Integer, String, ForeignKey, Enum, Time, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql.sqltypes import Date

from app.database import Base

# Core models
class AcademicYear(Base):
    __tablename__ = "academic_year"
    id = Column(Integer, primary_key=True, index=True)
    year = Column(String(20), nullable=False, unique=True)
    status = Column(Enum("Active", "Not Active"), nullable=False)
    
    semesters = relationship("Semester", back_populates="academic_year")

class Semester(Base):
    __tablename__ = "semester"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    academic_year_id = Column(Integer, ForeignKey("academic_year.id"), nullable=False)
    
    academic_year = relationship("AcademicYear", back_populates="semesters")
    courses = relationship("Course", back_populates="semester")

class Department(Base):
    __tablename__ = "department"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    
    programmes = relationship("Programme", back_populates="department")
    instructors = relationship("Instructor", back_populates="department")

class Programme(Base):
    __tablename__ = "programme"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    department_id = Column(Integer, ForeignKey("department.id"), nullable=False)
    
    department = relationship("Department", back_populates="programmes")
    courses = relationship("Course", back_populates="programme")

class Course(Base):
    __tablename__ = "course"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    type = Column(Enum("Theory", "Lab"), nullable=False)
    programme_id = Column(Integer, ForeignKey("programme.id"), nullable=False)
    semester_id = Column(Integer, ForeignKey("semester.id"), nullable=False)
    credit_hours = Column(Integer, nullable=False, default=3)
    expected_students = Column(Integer, nullable=True)
    
    programme = relationship("Programme", back_populates="courses")
    semester = relationship("Semester", back_populates="courses")
    timetable_entries = relationship("Timetable", back_populates="course")

class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    role = Column(Enum("Admin", "Faculty", "Student"), nullable=False)
    
    instructor = relationship("Instructor", back_populates="user", uselist=False)

class Instructor(Base):
    __tablename__ = "instructor"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), unique=True, nullable=False)
    department_id = Column(Integer, ForeignKey("department.id"), nullable=False)
    max_hours_per_week = Column(Integer, nullable=False, default=20)
    
    user = relationship("User", back_populates="instructor")
    department = relationship("Department", back_populates="instructors")
    timetable_entries = relationship("Timetable", back_populates="instructor")
    availability = relationship("InstructorAvailability", back_populates="instructor")
    preferences = relationship("InstructorPreference", back_populates="instructor")

class Room(Base):
    __tablename__ = "room"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, unique=True)
    capacity = Column(Integer, nullable=False)
    type = Column(Enum("Lecture Hall", "Lab"), nullable=False)
    
    timetable_entries = relationship("Timetable", back_populates="room")

class Timetable(Base):
    __tablename__ = "timetable"
    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(Integer, ForeignKey("course.id"), nullable=False)
    instructor_id = Column(Integer, ForeignKey("instructor.id"), nullable=False)
    room_id = Column(Integer, ForeignKey("room.id"), nullable=False)
    day = Column(Enum("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    semester_id = Column(Integer, ForeignKey("semester.id"), nullable=False)
    
    course = relationship("Course", back_populates="timetable_entries")
    instructor = relationship("Instructor", back_populates="timetable_entries")
    room = relationship("Room", back_populates="timetable_entries")
    semester = relationship("Semester")

# Additional models for optimization
class InstructorAvailability(Base):
    __tablename__ = "instructor_availability"
    id = Column(Integer, primary_key=True, index=True)
    instructor_id = Column(Integer, ForeignKey("instructor.id"), nullable=False)
    day = Column(Enum("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"), nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    is_available = Column(Boolean, nullable=False, default=True)
    
    instructor = relationship("Instructor", back_populates="availability")

class InstructorPreference(Base):
    __tablename__ = "instructor_preference"
    id = Column(Integer, primary_key=True, index=True)
    instructor_id = Column(Integer, ForeignKey("instructor.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("course.id"), nullable=False)
    preference_level = Column(Integer, nullable=False)  # 1-5 scale, 5 being highest preference
    
    instructor = relationship("Instructor", back_populates="preferences")
    course = relationship("Course")

class TimetableConstraint(Base):
    __tablename__ = "timetable_constraint"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    constraint_type = Column(Enum(
        "NoRoomConflict", 
        "NoInstructorConflict", 
        "RoomTypeMatch", 
        "InstructorAvailability",
        "InstructorMaxHours",
        "ConsecutiveCourses",
        "MinimizeGaps",
        "PreferredTimeSlots",
        "BalancedDistribution"
    ), nullable=False)
    is_hard_constraint = Column(Boolean, nullable=False, default=True)
    weight = Column(Integer, nullable=False, default=1)  # For soft constraints
    parameters = Column(Text, nullable=True)  # JSON encoded parameters

class TimetableGenerationJob(Base):
    __tablename__ = "timetable_generation_job"
    id = Column(Integer, primary_key=True, index=True)
    semester_id = Column(Integer, ForeignKey("semester.id"), nullable=False)
    created_at = Column(Date, nullable=False)
    completed_at = Column(Date, nullable=True)
    status = Column(Enum("Pending", "Running", "Completed", "Failed"), nullable=False)
    error_message = Column(Text, nullable=True)
    optimization_strategy = Column(String(50), nullable=False, default="balanced")
    result_metrics = Column(Text, nullable=True)  # JSON encoded metrics