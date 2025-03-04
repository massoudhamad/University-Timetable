# University Timetable Generator

A FastAPI application for automatically generating university timetables based on various constraints and preferences.

## Features

- Automatic timetable generation using constraint satisfaction
- Support for instructor preferences and availability
- Room allocation based on course requirements
- Multiple optimization strategies
- Conflict detection and resolution
- Detailed statistics and analysis
- REST API with full documentation

## Project Structure

```
university_timetable/
├── app/
│   ├── __init__.py
│   ├── main.py                # Application entry point
│   ├── database.py            # Database connection
│   ├── models.py              # SQLAlchemy ORM models
│   ├── schemas.py             # Pydantic schemas
│   ├── auth.py                # Authentication functions
│   ├── timetable_generator.py # Timetable generation algorithm
│   └── routers/               # API routes
│       ├── __init__.py
│       ├── router.py          # Main router
│       └── timetable.py       # Timetable endpoints
├── static/                    # Static files (optional)
└── README.md
```

## Prerequisites

- Python 3.8+
- PostgreSQL or SQLite
- Virtual environment (recommended)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/university_timetable.git
   cd university_timetable
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up environment variables (optional):
   ```bash
   # For PostgreSQL
   export DATABASE_URL="postgresql://user:password@localhost/timetable"
   
   # For JWT authentication
   export SECRET_KEY="your-secret-key"
   ```

5. Run the application:
   ```bash
   python -m app.main
   ```

6. Access the API documentation:
   ```
   http://localhost:8800/docs
   ```

## API Documentation

The API documentation is automatically generated and available at the `/docs` endpoint. It includes all endpoints, request/response models, and authentication requirements.

## Timetable Generation

The system uses a constraint-based algorithm to generate timetables. The process involves:

1. Loading all courses, instructors, and rooms
2. Prioritizing courses based on the selected strategy
3. Finding suitable time slots for each course
4. Respecting hard constraints (e.g., no room conflicts)
5. Optimizing for soft constraints (e.g., instructor preferences)

The generation can be customized with different strategies:
- `balanced`: Balanced approach (default)
- `rooms`: Prioritize efficient room utilization
- `instructors`: Prioritize instructor preferences
- `students`: Prioritize student experience

## Authentication

The API uses JWT-based authentication with role-based access control:
- Admin: Full access to all endpoints
- Faculty: Access to view timetables and manage their availability
- Student: Access to view timetables only

## Deployment

For production deployment, it's recommended to:
1. Use PostgreSQL instead of SQLite
2. Set a secure SECRET_KEY environment variable
3. Configure CORS with specific origins
4. Use a reverse proxy (e.g., Nginx) in front of the application
5. Run the application with a production ASGI server like Uvicorn or Hypercorn

## License

This project is licensed under the MIT License - see the LICENSE file for details.