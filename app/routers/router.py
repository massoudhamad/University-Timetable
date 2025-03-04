from fastapi import APIRouter
from app.routers import timetable

router = APIRouter()

# Include all sub-routers
router.include_router(timetable.router)

# Add more routers here as you develop them
# router.include_router(academic_year.router)
# router.include_router(semester.router)
# router.include_router(department.router)
# router.include_router(programme.router)
# router.include_router(course.router)
# router.include_router(instructor.router)
# router.include_router(room.router)
# router.include_router(user.router)