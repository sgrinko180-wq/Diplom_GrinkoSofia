from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Text, Date
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base
from sqlalchemy.orm import Session


class User(Base):
    __tablename__ = "users"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String)  # student, teacher, admin, head

    # Связи
    student = relationship("Student", back_populates="user", uselist=False)
    teacher = relationship("Teacher", back_populates="user", uselist=False)


class Teacher(Base):
    __tablename__ = "teachers"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String)
    user_id = Column(Integer, ForeignKey("users.id"))
    external_link = Column(String, nullable=True)

    # Связи
    user = relationship("User", back_populates="teacher")
    students = relationship("Student", back_populates="scientific_advisor")
    file_comments = relationship("FileComment", back_populates="teacher")
    teacher_files = relationship("TeacherFile", back_populates="teacher", cascade="all, delete-orphan")


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    meeting_date = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    student = relationship("Student", back_populates="meetings")
    tasks = relationship("Task", back_populates="meeting", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    meeting_id = Column(Integer, ForeignKey("meetings.id"))
    description = Column(Text, nullable=False)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    meeting = relationship("Meeting", back_populates="tasks")


class FileComment(Base):
    """Модель для заметок преподавателя к файлу студента"""
    __tablename__ = "file_comments"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    file_id = Column(Integer, ForeignKey("student_files.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=True)
    comment = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    file = relationship("StudentFile", back_populates="comments")
    teacher = relationship("Teacher", back_populates="file_comments")


class StudentFile(Base):
    """Модель для файлов, загруженных студентами"""
    __tablename__ = "student_files"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # pdf, archive, other
    file_size = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    teacher_note = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    student = relationship("Student", back_populates="files")
    comments = relationship("FileComment", back_populates="file", cascade="all, delete-orphan")


class TeacherFile(Base):
    """Модель для файлов, загруженных преподавателем (рекомендации)"""
    __tablename__ = "teacher_files"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id"), nullable=False)

    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=False)  # pdf, document, text, other
    file_size = Column(Integer, nullable=False)

    description = Column(Text, nullable=True)  # Описание/рекомендация

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Связи
    student = relationship("Student", back_populates="teacher_files")
    teacher = relationship("Teacher", back_populates="teacher_files")


class ArchivedWork(Base):
    """Архивная работа студента (курсовая/диплом прошлых лет)"""
    __tablename__ = "archived_works"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)

    # Связь со студентом
    student_id = Column(Integer, ForeignKey("students.id"))
    student = relationship("Student", back_populates="archived_works")

    # Основная информация
    academic_year = Column(String(9), nullable=False)  # "2021/2022"
    work_type = Column(String(50), nullable=False)  # "coursework" или "diploma"
    course = Column(Integer, nullable=False)  # Курс, на котором была работа

    # Детали работы
    title = Column(String(500), nullable=False)
    topic = Column(Text)
    supervisor_name = Column(String(200))  # Руководитель на тот момент

    # Файлы
    pdf_filename = Column(String(255))
    pdf_submitted = Column(Boolean, default=False)
    physical_submitted = Column(Boolean, default=False)

    # Оценки
    grade = Column(String(10))
    comments = Column(Text)

    # Статусы проверки
    plagiarism_checked = Column(Boolean, default=False)
    annotation_submitted = Column(Boolean, default=False)

    # Даты
    submission_date = Column(Date)
    defense_date = Column(Date)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Student(Base):
    __tablename__ = "students"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String)
    course = Column(Integer)
    topic = Column(String, nullable=True)
    pdf_submitted = Column(Boolean, default=False)
    physical_submitted = Column(Boolean, default=False)
    plagiarism_checked = Column(Boolean, default=False)
    annotation_submitted = Column(Boolean, default=False)
    user_id = Column(Integer, ForeignKey("users.id"))
    advisor_id = Column(Integer, ForeignKey("teachers.id"))
    last_call_date = Column(Date, nullable=True)
    current_academic_year = Column(String(9), default=lambda: f"{datetime.now().year}/{datetime.now().year + 1}")

    # Связи
    user = relationship("User", back_populates="student")
    scientific_advisor = relationship("Teacher", back_populates="students")
    meetings = relationship("Meeting", back_populates="student", cascade="all, delete-orphan")
    archived_works = relationship("ArchivedWork", back_populates="student", cascade="all, delete-orphan")
    files = relationship("StudentFile", back_populates="student", cascade="all, delete-orphan")
    teacher_files = relationship("TeacherFile", back_populates="student", cascade="all, delete-orphan")

    def get_call_activity_status(self, db_session=None) -> str:
        """
        Определяет статус активности созвонов:
        - 'no_calls': давно не было созвонов (> 30 дней) или нет созвонов
        - 'irregular_calls': нерегулярные созвоны (< 2 за 30 дней)
        - 'regular_calls': регулярные созвоны (≥ 2 за 30 дней)
        """
        from datetime import datetime, timedelta

        if db_session is None:
            from .database import SessionLocal
            db = SessionLocal()
            try:
                return self._calculate_activity_status(db)
            finally:
                db.close()
        else:
            return self._calculate_activity_status(db_session)

    def _calculate_activity_status(self, db_session) -> str:
        from datetime import datetime, timedelta

        meetings = db_session.query(Meeting).filter(
            Meeting.student_id == self.id
        ).order_by(Meeting.meeting_date.desc()).all()

        if not meetings:
            return 'no_calls'

        last_meeting = meetings[0].meeting_date
        now = datetime.utcnow()

        days_since_last_call = (now - last_meeting).days

        if days_since_last_call > 30:
            return 'no_calls'

        month_ago = now - timedelta(days=30)
        recent_calls = [
            m for m in meetings
            if m.meeting_date >= month_ago
        ]

        if len(recent_calls) < 2:
            return 'irregular_calls'
        else:
            return 'regular_calls'

class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(String(50),
                  nullable=False)  # task_added, task_completed, task_redone, meeting_added, file_added, etc.
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    link = Column(String(500), nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Связь с пользователем
    user = relationship("User", backref="notifications")