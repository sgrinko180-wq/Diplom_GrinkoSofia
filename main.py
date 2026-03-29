from .database import engine, SessionLocal
from . import models
models.Base.metadata.create_all(bind=engine)
from fastapi import FastAPI, Request, Form, HTTPException, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from itsdangerous import URLSafeSerializer
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
import json
from .models import User, Student, Teacher, Meeting, Task, StudentFile, TeacherFile, ArchivedWork, Notification
app = FastAPI(title="Diploma Management System")
templates = Jinja2Templates(directory="templates")

templates.env.globals.update({
    "now": datetime.now,
    "datetime": datetime,
    "timedelta": timedelta,
    "len": len,
    "enumerate": enumerate,
    "range": range,
    "str": str,
    "int": int,
    "list": list,
    "dict": dict,
})
app.mount("/static", StaticFiles(directory="app/static"), name="static")

SECRET_KEY = "my_super_secret_key"
serializer = URLSafeSerializer(SECRET_KEY, salt="user-session")



def get_current_user(request: Request):
    cookie = request.cookies.get("session")
    if not cookie:
        return None
    try:
        data = serializer.loads(cookie)
        user_id = data.get("user_id")
        db = SessionLocal()
        user = db.query(models.User).filter(models.User.id == user_id).first()

        if user:
            if user.role == "student" and user.student:
                user.full_name = user.student.full_name
                user.student_object = user.student
            elif user.role == "teacher" and user.teacher:
                user.full_name = user.teacher.full_name
                user.teacher_object = user.teacher
            elif user.role == "admin":
                user.full_name = "Администратор"
            else:
                user.full_name = user.email
            user.role = user.role

        db.close()
        return user
    except Exception as e:
        print(f"Error getting current user: {e}")
        return None


def create_notification(db: Session, user_id: int, type: str, title: str, message: str, link: str = None):
    """Создать новое уведомление"""
    from .models import Notification
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        link=link,
        is_read=False
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification
# --- Главная ---
@app.get("/main", response_class=HTMLResponse)
def index(request: Request):
    user = get_current_user(request)
    return templates.TemplateResponse("main.html", {"request": request, "current_user": user})


# --- Список студентов ---
@app.get("/", response_class=HTMLResponse, name="students")
def students_list(request: Request):
    db = SessionLocal()
    students = db.query(models.Student).all()
    result = []

    for s in students:
        advisor_link = s.scientific_advisor.external_link if s.scientific_advisor else "#"
        result.append({
            "id": s.id,
            "full_name": s.full_name,
            "course": s.course,
            "topic": s.topic,
            "advisor_name": s.scientific_advisor.full_name if s.scientific_advisor else "—",
            "advisor_link": advisor_link
        })
    db.close()
    return templates.TemplateResponse(
        "students.html",
        {"request": request, "students": result, "current_user": get_current_user(request)}
    )


# --- Карточка студента ---
@app.get("/student/{student_id}", response_class=HTMLResponse)
def student_card(request: Request, student_id: int):
    db = SessionLocal()

    try:
        s = db.query(models.Student).filter(models.Student.id == student_id).first()
        if not s:
            db.close()
            raise HTTPException(status_code=404, detail="Студент не найден")
        work_type = "diploma" if s.course == 4 else "coursework"
        student = {
            "id": s.id,
            "full_name": s.full_name,
            "course": s.course,
            "topic": s.topic,
            "work_type": work_type,
            "advisor_name": s.scientific_advisor.full_name if s.scientific_advisor else "—",
            "advisor_link": s.scientific_advisor.external_link if s.scientific_advisor else "#",
            "pdf_submitted": s.pdf_submitted,
            "physical_submitted": s.physical_submitted,
            "plagiarism_checked": s.plagiarism_checked,
            "annotation_submitted": s.annotation_submitted
        }
        archive_works = []

        try:
            archive_query = db.query(models.ArchivedWork).filter(
                models.ArchivedWork.student_id == student_id
            ).order_by(
                models.ArchivedWork.academic_year.desc(),
                models.ArchivedWork.course.desc()
            ).all()

            for work in archive_query:
                archive_works.append({
                    "academic_year": work.academic_year,
                    "course": work.course,
                    "work_type": work.work_type,
                    "title": work.title,
                    "topic": work.topic,
                    "supervisor_name": work.supervisor_name,
                    "grade": work.grade,
                    "pdf_submitted": work.pdf_submitted,
                    "physical_submitted": work.physical_submitted,
                    "comments": work.comments,
                    "plagiarism_checked": work.plagiarism_checked,
                    "annotation_submitted": work.annotation_submitted
                })

            print(f"Найдено {len(archive_works)} архивных работ для студента {student_id}")

        except Exception as e:
            print(f"Ошибка при загрузке архива: {e}")
            archive_works = []

        current_year = datetime.now().year
        current_academic_year = f"{current_year - 1}/{current_year}"

        print(f"Текущий учебный год: {current_academic_year}")

        db.close()

        return templates.TemplateResponse(
            "student_card.html",
            {
                "request": request,
                "student": student,
                "archive_works": archive_works,
                "current_user": get_current_user(request),
                "current_academic_year": current_academic_year  # ЭТА СТРОКА ДОЛЖНА БЫТЬ
            }
        )

    except Exception as e:
        db.close()
        print(f"Общая ошибка в student_card: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка сервера: {str(e)}")
# GET форма входа
@app.get("/login", response_class=HTMLResponse, name="login_get")
def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


# --- POST входа ---
@app.post("/login", response_class=HTMLResponse, name="login_post")
def login_post(request: Request, email: str = Form(...), password: str = Form(...)):
    db = SessionLocal()
    user = db.query(models.User).filter(models.User.email == email).first()
    db.close()

    if not user:
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Неверный email или пароль"}
        )
    if user.role == "admin":
        if password != user.hashed_password:
            return templates.TemplateResponse(
                "login.html", {"request": request, "error": "Неверный email или пароль"}
            )
    else:
        if password != "fakehashedpassword":
            return templates.TemplateResponse(
                "login.html", {"request": request, "error": "Неверный email или пароль"}
            )

    data = {"user_id": user.id, "role": user.role}
    cookie_value = serializer.dumps(data)

    redirect_url = "/"
    if user.role == "admin" or user.role == "teacher":
        redirect_url = "/my-students"
    elif user.role == "student":
        redirect_url = "/student-work"

    response = RedirectResponse(url=redirect_url, status_code=302)
    response.set_cookie(key="session", value=cookie_value, httponly=True, max_age=3600 * 24, path="/")
    return response

# --- Выход из системы ---
@app.get("/logout")
def logout():
    response = RedirectResponse(url="/")
    response.delete_cookie(key="session", path="/")
    return response


# --- Мои студенты (для преподавателей) ---
# --- Мои студенты (для преподавателей) ---
@app.get("/my-students", response_class=HTMLResponse)
def my_students(request: Request):
    user = get_current_user(request)

    if not user or (user.role != "teacher" and user.role != "admin"):
        return RedirectResponse(url="/login")

    db = SessionLocal()

    try:
        if user.role == "admin":
            teacher_name = "Администратор (все студенты)"  # Это только для заголовка
            students_query = db.query(models.Student) \
                .order_by(models.Student.course, models.Student.full_name) \
                .all()
        else:
            teacher = db.query(models.Teacher) \
                .filter(models.Teacher.user_id == user.id) \
                .first()

            if not teacher:
                db.close()
                return templates.TemplateResponse(
                    "error.html",
                    {"request": request, "error": "Преподаватель не найден"}
                )

            teacher_name = teacher.full_name
            students_query = db.query(models.Student) \
                .filter(models.Student.advisor_id == teacher.id) \
                .order_by(models.Student.course, models.Student.full_name) \
                .all()

        result = []
        for s in students_query:
            call_status = "no_calls"
            meetings = db.query(models.Meeting) \
                .filter(models.Meeting.student_id == s.id) \
                .order_by(models.Meeting.meeting_date.desc()) \
                .all()

            if meetings:
                last_meeting = meetings[0].meeting_date
                now = datetime.utcnow()
                days_since_last_call = (now - last_meeting).days

                if days_since_last_call > 30:
                    call_status = 'no_calls'
                else:
                    month_ago = now - timedelta(days=30)
                    recent_calls = [
                        m for m in meetings
                        if m.meeting_date >= month_ago
                    ]

                    if len(recent_calls) < 2:
                        call_status = 'irregular_calls'
                    else:
                        call_status = 'regular_calls'

            status_class = {
                'no_calls': 'status-no-calls',
                'irregular_calls': 'status-irregular-calls',
                'regular_calls': 'status-regular-calls'
            }.get(call_status, '')

            status_label = {
                'no_calls': 'Давно не было встреч',
                'irregular_calls': 'Нерегулярные встречи',
                'regular_calls': 'Регулярные встречи'
            }.get(call_status, '')
            archived_works_count = db.query(models.ArchivedWork) \
                .filter(models.ArchivedWork.student_id == s.id) \
                .count()

            # ИСПРАВЛЕНИЕ ЗДЕСЬ: для администратора подставляем реальное имя руководителя
            if user.role == "admin":
                advisor_name = s.scientific_advisor.full_name if s.scientific_advisor else "—"
            else:
                advisor_name = s.scientific_advisor.full_name if s.scientific_advisor else "—"

            result.append({
                "id": s.id,
                "full_name": s.full_name,
                "course": s.course,
                "topic": s.topic,
                "advisor_name": advisor_name,  # Теперь всегда реальное имя
                "advisor_link": s.scientific_advisor.external_link if s.scientific_advisor else "#",
                "pdf_submitted": s.pdf_submitted,
                "physical_submitted": s.physical_submitted,
                "plagiarism_checked": s.plagiarism_checked,
                "annotation_submitted": s.annotation_submitted,
                "call_status": call_status,
                "call_status_class": status_class,
                "call_status_label": status_label,
                "archived_works_count": archived_works_count,
            })

        status_order = {'no_calls': 0, 'irregular_calls': 1, 'regular_calls': 2}
        result.sort(key=lambda x: status_order.get(x['call_status'], 3))

        db.close()

        return templates.TemplateResponse(
            "my_students.html",
            {
                "request": request,
                "students": result,
                "current_user": user,
                "teacher_name": teacher_name,  # Это только для заголовка
                "is_admin": user.role == "admin"
            }
        )

    except Exception as e:
        db.close()
        print(f"Error in my_students: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(e)}
        )
from fastapi import FastAPI, Request, Form, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import json

class StudentStatusUpdate(BaseModel):
    student_id: int
    pdf_submitted: Optional[bool] = None
    physical_submitted: Optional[bool] = None
    plagiarism_checked: Optional[bool] = None
    annotation_submitted: Optional[bool] = None


# Endpoint для обновления статусов студента
@app.post("/update-student-status")
async def update_student_status(
        status_data: StudentStatusUpdate,
        request: Request
):
    user = get_current_user(request)
    if not user or (user.role != "teacher" and user.role != "admin"):
        return {"success": False, "error": "Только преподаватели или администраторы могут обновлять статусы"}

    db = SessionLocal()

    try:
        student = db.query(models.Student).filter(models.Student.id == status_data.student_id).first()

        if not student:
            return {"success": False, "error": "Студент не найден"}
        if user.role == "teacher" and student.advisor_id != user.teacher_object.id:
            return {"success": False, "error": "Вы не являетесь научным руководителем этого студента"}
        if user.role == "teacher" and student.course < 4:
            if status_data.plagiarism_checked is not None:
                return {"success": False, "error": "Проверка плагиата доступна только для 4 курса"}
            if status_data.annotation_submitted is not None:
                return {"success": False, "error": "Сдача аннотации доступна только для 4 курса"}

        if status_data.pdf_submitted is not None:
            student.pdf_submitted = status_data.pdf_submitted

        if status_data.physical_submitted is not None:
            student.physical_submitted = status_data.physical_submitted

        if user.role == "admin" or student.course == 4:
            if status_data.plagiarism_checked is not None:
                student.plagiarism_checked = status_data.plagiarism_checked

            if status_data.annotation_submitted is not None:
                student.annotation_submitted = status_data.annotation_submitted

        db.commit()

        return {
            "success": True,
            "message": "Статус обновлен",
            "student_id": student.id,
            "course": student.course,
            "updated_by": user.role
        }

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()

from typing import Optional
from pydantic import BaseModel
class StudentTopicUpdate(BaseModel):
    student_id: int
    topic: Optional[str] = None

# Endpoint для обновления темы
@app.post("/update-student-topic")
async def update_student_topic(
        topic_data: StudentTopicUpdate,
        request: Request
):
    user = get_current_user(request)
    if not user or (user.role != "teacher" and user.role != "admin"):
        return {"success": False, "error": "Только преподаватели или администраторы могут обновлять темы"}

    db = SessionLocal()

    try:
        student = db.query(models.Student).filter(models.Student.id == topic_data.student_id).first()

        if not student:
            return {"success": False, "error": "Студент не найден"}
        if user.role == "teacher":
            if student.advisor_id != user.teacher_object.id:
                return {"success": False, "error": "Вы не являетесь научным руководителем этого студента"}
        old_topic = student.topic

        if topic_data.topic is None:
            student.topic = None
        else:
            cleaned_topic = topic_data.topic.strip()
            if cleaned_topic == "" or cleaned_topic.lower() == "не выбрана":
                student.topic = None
            else:
                student.topic = cleaned_topic

        db.commit()

        return {
            "success": True,
            "message": "Тема обновлена",
            "student_id": student.id,
            "old_topic": old_topic,
            "new_topic": student.topic,
            "updated_by": user.role
        }

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()

class MeetingCreate(BaseModel):
    student_id: int
    meeting_date: str
    notes: Optional[str] = None


class MeetingNotesUpdate(BaseModel):
    meeting_id: int
    notes: str


class TaskCreate(BaseModel):
    meeting_id: int
    description: str


class TaskToggle(BaseModel):
    task_id: int
    is_completed: bool


@app.get("/teacher/student/{student_id}", response_class=HTMLResponse)
def teacher_student_detail(request: Request, student_id: int):
    user = get_current_user(request)
    if not user or user.role != "teacher":
        return RedirectResponse(url="/login")

    db = SessionLocal()

    try:
        student = db.query(models.Student).filter(models.Student.id == student_id).first()

        if not student:
            raise HTTPException(status_code=404, detail="Студент не найден")

        if student.advisor_id != user.teacher_object.id:
            return RedirectResponse(url="/my-students")

        meetings = db.query(models.Meeting) \
            .filter(models.Meeting.student_id == student_id) \
            .order_by(models.Meeting.meeting_date.desc()) \
            .all()

        for meeting in meetings:
            meeting.tasks = db.query(models.Task) \
                .filter(models.Task.meeting_id == meeting.id) \
                .order_by(models.Task.created_at) \
                .all()

        total_tasks = 0
        completed_tasks = 0

        for meeting in meetings:
            total_tasks += len(meeting.tasks)
            completed_tasks += sum(1 for task in meeting.tasks if task.is_completed)

        completion_rate = round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0)
        archived_works = db.query(models.ArchivedWork) \
            .filter(models.ArchivedWork.student_id == student_id) \
            .order_by(models.ArchivedWork.academic_year.desc(),
                      models.ArchivedWork.course.desc()) \
            .all()
        return templates.TemplateResponse(
            "teacher_student_detail.html",
            {
                "request": request,
                "student": student,
                "meetings": meetings,
                "archived_works": archived_works,
                "current_user": user,
                "total_tasks_count": total_tasks,
                "completed_tasks_count": completed_tasks,
                "completion_rate": completion_rate
            }
        )

    finally:
        db.close()

# Endpoint для добавления созвона
@app.post("/add-meeting")
async def add_meeting(request: Request):
    data = await request.json()
    student_id = data.get('student_id')
    meeting_date_str = data.get('meeting_date')
    notes = data.get('notes', '')

    user = get_current_user(request)
    if not user:
        return {"success": False, "error": "Требуется авторизация"}

    db = SessionLocal()
    try:
        from datetime import datetime
        meeting_date = datetime.fromisoformat(meeting_date_str)
        new_meeting = Meeting(
            student_id=student_id,
            meeting_date=meeting_date,
            notes=notes
        )
        db.add(new_meeting)
        db.commit()
        db.refresh(new_meeting)
        student = db.query(Student).filter(Student.id == student_id).first()
        if student and student.user_id:
            teacher_name = user.full_name or "Преподаватель"
            meeting_date_str = meeting_date.strftime('%d.%m.%Y %H:%M')

            create_notification(
                db=db,
                user_id=student.user_id,
                type="meeting_added",
                title="Новая встреча",
                message=f"{teacher_name}: встреча назначена на {meeting_date_str}",
                link="/student-work"
            )

        return {"success": True, "meeting_id": new_meeting.id}

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()
# Endpoint для обновления заметок созвона
@app.post("/update-meeting-notes")
async def update_meeting_notes(notes_data: MeetingNotesUpdate, request: Request):
    user = get_current_user(request)
    if not user or user.role != "teacher":
        return {"success": False, "error": "Только преподаватели могут обновлять заметки"}

    db = SessionLocal()

    try:
        meeting = db.query(models.Meeting).filter(models.Meeting.id == notes_data.meeting_id).first()
        if not meeting:
            return {"success": False, "error": "Встреча не найден"}

        student = db.query(models.Student).filter(models.Student.id == meeting.student_id).first()
        if not student or student.advisor_id != user.teacher_object.id:
            return {"success": False, "error": "У вас нет доступа к этой встречи"}

        meeting.notes = notes_data.notes
        db.commit()

        return {
            "success": True,
            "message": "Заметки обновлены"
        }

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()


# Endpoint для добавления задачи
@app.post("/add-task")
async def add_task(request: Request):
    data = await request.json()
    meeting_id = data.get('meeting_id')
    description = data.get('description')

    user = get_current_user(request)
    if not user:
        return {"success": False, "error": "Требуется авторизация"}

    db = SessionLocal()
    try:
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if not meeting:
            return {"success": False, "error": "Встреча не найдена"}

        student = db.query(Student).filter(Student.id == meeting.student_id).first()
        if not student:
            return {"success": False, "error": "Студент не найден"}

        new_task = Task(
            meeting_id=meeting_id,
            description=description,
            is_completed=False
        )
        db.add(new_task)
        db.commit()
        db.refresh(new_task)
        teacher_name = user.full_name or "Преподаватель"
        student_user_id = student.user_id  # ID пользователя-студента

        create_notification(
            db=db,
            user_id=student_user_id,
            type="task_added",
            title="Новая задача",
            message=f"{teacher_name}: {description[:50]}...",
            link="/student-work"
        )

        return {"success": True, "task_id": new_task.id}

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()

# Endpoint для переключения статуса задачи
@app.post("/toggle-task")
async def toggle_task(task_data: TaskToggle, request: Request):
    user = get_current_user(request)
    if not user:
        return {"success": False, "error": "Требуется авторизация"}

    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.id == task_data.task_id).first()
        if not task:
            return {"success": False, "error": "Задача не найдена"}
        meeting = db.query(Meeting).filter(Meeting.id == task.meeting_id).first()
        if not meeting:
            return {"success": False, "error": "Встреча не найдена"}

        student = db.query(Student).filter(Student.id == meeting.student_id).first()
        if not student:
            return {"success": False, "error": "Студент не найден"}

        was_completed = task.is_completed

        task.is_completed = task_data.is_completed
        if task_data.is_completed:
            from datetime import datetime
            task.completed_at = datetime.utcnow()
        else:
            task.completed_at = None

        db.commit()

        # СОЗДАЕМ УВЕДОМЛЕНИЯ
        if user.role == "teacher" and was_completed and not task_data.is_completed:
            teacher_name = user.full_name or "Преподаватель"
            student_user_id = student.user_id

            create_notification(
                db=db,
                user_id=student_user_id,
                type="task_redone",
                title="Задача на доработку",
                message=f"{teacher_name}: Задача '{task.description[:40]}...' отправлена на доработку",
                link="/student-work"
            )

        if user.role == "student" and not was_completed and task_data.is_completed:
            teacher = db.query(Teacher).filter(Teacher.id == student.advisor_id).first()
            if teacher and teacher.user_id:
                student_name = student.full_name

                create_notification(
                    db=db,
                    user_id=teacher.user_id,
                    type="task_completed",
                    title="Задача выполнена",
                    message=f"{student_name}: {task.description[:50]}...",
                    link=f"/teacher/student/{student.user_id}"
                )

        return {
            "success": True,
            "message": "Статус задачи обновлен",
            "is_completed": task.is_completed,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None
        }

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()
# Endpoint для удаления задачи
@app.delete("/delete-task/{task_id}")
async def delete_task(task_id: int, request: Request):
    user = get_current_user(request)
    if not user or user.role != "teacher":
        return {"success": False, "error": "Только преподаватели могут удалять задачи"}

    db = SessionLocal()

    try:
        task = db.query(models.Task).filter(models.Task.id == task_id).first()
        if not task:
            return {"success": False, "error": "Задача не найдена"}

        meeting = db.query(models.Meeting).filter(models.Meeting.id == task.meeting_id).first()
        if not meeting:
            return {"success": False, "error": "Встреча не найден"}
        student = db.query(models.Student).filter(models.Student.id == meeting.student_id).first()
        if not student or student.advisor_id != user.teacher_object.id:
            return {"success": False, "error": "У вас нет доступа к этой задаче"}

        db.delete(task)
        db.commit()

        return {
            "success": True,
            "message": "Задача удалена"
        }

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()


# Endpoint для получения статистики студента
@app.get("/get-student-statistics/{student_id}")
async def get_student_statistics(student_id: int, request: Request):
    user = get_current_user(request)
    if not user:
        return {"success": False, "error": "Требуется авторизация"}

    db = SessionLocal()

    try:
        meetings = db.query(models.Meeting) \
            .filter(models.Meeting.student_id == student_id) \
            .all()

        total_tasks = 0
        completed_tasks = 0

        for meeting in meetings:
            tasks = db.query(models.Task) \
                .filter(models.Task.meeting_id == meeting.id) \
                .all()

            total_tasks += len(tasks)
            completed_tasks += sum(1 for task in tasks if task.is_completed)

        completion_rate = round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0)

        return {
            "success": True,
            "meetings_count": len(meetings),
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "completion_rate": completion_rate
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        db.close()


# --- Страница "Работа" для студента ---
@app.get("/student-work", response_class=HTMLResponse)
def student_work(request: Request):
    user = get_current_user(request)

    if not user or user.role != "student":
        return RedirectResponse(url="/login")

    db = SessionLocal()

    try:
        student = db.query(models.Student).filter(models.Student.user_id == user.id).first()

        if not student:
            return templates.TemplateResponse(
                "error.html",
                {"request": request, "error": "Студент не найден"}
            )

        advisor = None
        if student.advisor_id:
            advisor = db.query(models.Teacher).filter(models.Teacher.id == student.advisor_id).first()

        meetings = db.query(models.Meeting) \
            .filter(models.Meeting.student_id == student.id) \
            .order_by(models.Meeting.meeting_date.desc()) \
            .all()

        for meeting in meetings:
            meeting.tasks = db.query(models.Task) \
                .filter(models.Task.meeting_id == meeting.id) \
                .order_by(models.Task.created_at) \
                .all()

        total_tasks = 0
        completed_tasks = 0

        for meeting in meetings:
            total_tasks += len(meeting.tasks)
            completed_tasks += sum(1 for task in meeting.tasks if task.is_completed)

        completion_rate = round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0)
        return templates.TemplateResponse(
            "student_work.html",
            {
                "request": request,
                "student": student,
                "advisor": advisor,
                "meetings": meetings,
                "current_user": user,
                "total_tasks_count": total_tasks,
                "completed_tasks_count": completed_tasks,
                "completion_rate": completion_rate
            }
        )

    finally:
        db.close()


def check_teacher_or_admin_access(user, student_id=None):
    """
    Проверяет, имеет ли пользователь доступ к функциям преподавателя.
    Для администратора - всегда True.
    Для преподавателя - проверяет, является ли он научным руководителем студента.
    """
    if not user:
        return False

    if user.role == "admin":
        return True

    if user.role == "teacher":
        if student_id:
            db = SessionLocal()
            student = db.query(models.Student).filter(models.Student.id == student_id).first()
            db.close()
            if student and student.advisor_id == user.teacher_object.id:
                return True
            return False
        return True

    return False

def get_all_students_for_admin():
    """Возвращает всех студентов для администратора"""
    db = SessionLocal()
    students = db.query(models.Student).all()
    result = []

    for s in students:
        advisor_link = s.scientific_advisor.external_link if s.scientific_advisor else "#"
        result.append({
            "id": s.id,
            "full_name": s.full_name,
            "course": s.course,
            "topic": s.topic,
            "advisor_name": s.scientific_advisor.full_name if s.scientific_advisor else "—",
            "advisor_link": advisor_link,
            "pdf_submitted": s.pdf_submitted,
            "physical_submitted": s.physical_submitted,
            "plagiarism_checked": s.plagiarism_checked,
            "annotation_submitted": s.annotation_submitted,
        })

    db.close()
    return result


# --- POST входа ---
@app.post("/login", response_class=HTMLResponse, name="login_post")
def login_post(request: Request, email: str = Form(...), password: str = Form(...)):
    db = SessionLocal()
    user = db.query(models.User).filter(models.User.email == email).first()
    db.close()

    if not user or user.hashed_password != password:
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Неверный email или пароль"}
        )

    data = {"user_id": user.id, "role": user.role}
    cookie_value = serializer.dumps(data)

    redirect_url = "/"
    if user.role == "admin" or user.role == "teacher":
        redirect_url = "/my-students"
    elif user.role == "student":
        redirect_url = "/student-work"

    response = RedirectResponse(url=redirect_url, status_code=302)
    response.set_cookie(key="session", value=cookie_value, httponly=True, max_age=3600 * 24, path="/")
    return response
@app.get("/admin/student/{student_id}", response_class=HTMLResponse)
def admin_student_detail(request: Request, student_id: int):
    user = get_current_user(request)

    if not user or user.role != "admin":
        return RedirectResponse(url="/login")

    db = SessionLocal()

    try:
        student = db.query(models.Student).filter(models.Student.id == student_id).first()

        if not student:
            raise HTTPException(status_code=404, detail="Студент не найден")

        advisor = None
        if student.advisor_id:
            advisor = db.query(models.Teacher).filter(models.Teacher.id == student.advisor_id).first()

        meetings = db.query(models.Meeting) \
            .filter(models.Meeting.student_id == student_id) \
            .order_by(models.Meeting.meeting_date.desc()) \
            .all()

        for meeting in meetings:
            meeting.tasks = db.query(models.Task) \
                .filter(models.Task.meeting_id == meeting.id) \
                .order_by(models.Task.created_at) \
                .all()

        total_tasks = 0
        completed_tasks = 0

        for meeting in meetings:
            total_tasks += len(meeting.tasks)
            completed_tasks += sum(1 for task in meeting.tasks if task.is_completed)

        completion_rate = round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0)

        return templates.TemplateResponse(
            "admin_student_detail.html",
            {
                "request": request,
                "student": student,
                "advisor": advisor,
                "meetings": meetings,
                "current_user": user,
                "total_tasks_count": total_tasks,
                "completed_tasks_count": completed_tasks,
                "completion_rate": completion_rate
            }
        )

    finally:
        db.close()


# --- Страница преподавателей для администратора ---
# --- Страница преподавателей для администратора ---
@app.get("/admin/teachers", response_class=HTMLResponse)
def admin_teachers(request: Request):
    user = get_current_user(request)

    if not user or user.role != "admin":
        return RedirectResponse(url="/login")

    db = SessionLocal()

    try:
        teachers = db.query(models.Teacher).all()
        teachers_with_stats = []

        for teacher in teachers:
            students = db.query(models.Student).filter(models.Student.advisor_id == teacher.id).all()

            total_students = len(students)

            # Статистика по курсам
            students_by_course = {2: 0, 3: 0, 4: 0}
            topics_selected = 0
            topics_not_selected = 0

            # Статистика по встречам
            no_calls_count = 0
            irregular_calls_count = 0
            regular_calls_count = 0

            for student in students:
                if student.course in students_by_course:
                    students_by_course[student.course] += 1

                if student.topic:
                    topics_selected += 1
                else:
                    topics_not_selected += 1

                # Вычисляем статус встреч для каждого студента
                meetings = db.query(models.Meeting) \
                    .filter(models.Meeting.student_id == student.id) \
                    .order_by(models.Meeting.meeting_date.desc()) \
                    .all()

                if meetings:
                    last_meeting = meetings[0].meeting_date
                    now = datetime.utcnow()
                    days_since_last_call = (now - last_meeting).days

                    if days_since_last_call > 30:
                        no_calls_count += 1
                    else:
                        month_ago = now - timedelta(days=30)
                        recent_calls = [
                            m for m in meetings
                            if m.meeting_date >= month_ago
                        ]

                        if len(recent_calls) < 2:
                            irregular_calls_count += 1
                        else:
                            regular_calls_count += 1
                else:
                    # Если встреч вообще нет, считаем как "давно не звонили"
                    no_calls_count += 1

            pdf_submitted = sum(1 for s in students if s.pdf_submitted)
            physical_submitted = sum(1 for s in students if s.physical_submitted)
            plagiarism_checked = sum(1 for s in students if s.plagiarism_checked)
            annotation_submitted = sum(1 for s in students if s.annotation_submitted)

            fourth_year_students = [s for s in students if s.course == 4]
            fourth_year_count = len(fourth_year_students)
            fourth_year_plagiarism = sum(1 for s in fourth_year_students if s.plagiarism_checked)
            fourth_year_annotation = sum(1 for s in fourth_year_students if s.annotation_submitted)

            teachers_with_stats.append({
                "id": teacher.id,
                "full_name": teacher.full_name,
                "external_link": teacher.external_link,
                "total_students": total_students,
                "students_by_course": students_by_course,
                "topics_selected": topics_selected,
                "topics_not_selected": topics_not_selected,
                "pdf_submitted": pdf_submitted,
                "physical_submitted": physical_submitted,
                "plagiarism_checked": plagiarism_checked,
                "annotation_submitted": annotation_submitted,
                "fourth_year_count": fourth_year_count,
                "fourth_year_plagiarism": fourth_year_plagiarism,
                "fourth_year_annotation": fourth_year_annotation,
                "topic_percentage": round((topics_selected / total_students * 100) if total_students > 0 else 0, 1),
                "completion_percentage": round((pdf_submitted / total_students * 100) if total_students > 0 else 0, 1),
                # Добавляем статистику по встречам
                "no_calls_count": no_calls_count,
                "irregular_calls_count": irregular_calls_count,
                "regular_calls_count": regular_calls_count,
                "meetings_total": no_calls_count + irregular_calls_count + regular_calls_count
            })

        # Сортируем преподавателей по количеству студентов (по убыванию)
        teachers_with_stats.sort(key=lambda x: x["total_students"], reverse=True)

        # Общая статистика по встречам для всех преподавателей
        total_no_calls = sum(t["no_calls_count"] for t in teachers_with_stats)
        total_irregular_calls = sum(t["irregular_calls_count"] for t in teachers_with_stats)
        total_regular_calls = sum(t["regular_calls_count"] for t in teachers_with_stats)

        total_teachers = len(teachers_with_stats)
        total_all_students = sum(t["total_students"] for t in teachers_with_stats)
        avg_students_per_teacher = round(total_all_students / total_teachers if total_teachers > 0 else 0, 1)

        return templates.TemplateResponse(
            "admin_teachers.html",
            {
                "request": request,
                "teachers": teachers_with_stats,
                "current_user": user,
                "total_teachers": total_teachers,
                "total_all_students": total_all_students,
                "avg_students_per_teacher": avg_students_per_teacher,
                # Добавляем общую статистику по встречам
                "total_no_calls": total_no_calls,
                "total_irregular_calls": total_irregular_calls,
                "total_regular_calls": total_regular_calls
            }
        )

    finally:
        db.close()

# --- Студенты конкретного преподавателя (для администратора) ---
# --- Студенты конкретного преподавателя (для администратора) ---
@app.get("/admin/teacher/{teacher_id}/students", response_class=HTMLResponse)
def admin_teacher_students(request: Request, teacher_id: int):
    user = get_current_user(request)

    if not user or user.role != "admin":
        return RedirectResponse(url="/login")

    db = SessionLocal()

    try:
        teacher = db.query(models.Teacher).filter(models.Teacher.id == teacher_id).first()

        if not teacher:
            raise HTTPException(status_code=404, detail="Преподаватель не найден")

        students = db.query(models.Student) \
            .filter(models.Student.advisor_id == teacher_id) \
            .order_by(models.Student.course, models.Student.full_name) \
            .all()

        students_by_course = {}
        total_students = len(students)

        # Собираем всех студентов для статистики по встречам
        all_students_with_status = []

        for student in students:
            course = student.course
            if course not in students_by_course:
                students_by_course[course] = []

            # Вычисляем статус встреч для каждого студента (как в my_students)
            call_status = "no_calls"
            meetings = db.query(models.Meeting) \
                .filter(models.Meeting.student_id == student.id) \
                .order_by(models.Meeting.meeting_date.desc()) \
                .all()

            if meetings:
                last_meeting = meetings[0].meeting_date
                now = datetime.utcnow()
                days_since_last_call = (now - last_meeting).days

                if days_since_last_call > 30:
                    call_status = 'no_calls'
                else:
                    month_ago = now - timedelta(days=30)
                    recent_calls = [
                        m for m in meetings
                        if m.meeting_date >= month_ago
                    ]

                    if len(recent_calls) < 2:
                        call_status = 'irregular_calls'
                    else:
                        call_status = 'regular_calls'

            status_label = {
                'no_calls': 'Давно не было встреч',
                'irregular_calls': 'Нерегулярные встречи',
                'regular_calls': 'Регулярные встречи'
            }.get(call_status, '')

            advisor_link = teacher.external_link if teacher else "#"

            student_data = {
                "id": student.id,
                "full_name": student.full_name,
                "course": student.course,
                "topic": student.topic,
                "advisor_name": teacher.full_name if teacher else "—",
                "advisor_link": advisor_link,
                "pdf_submitted": student.pdf_submitted,
                "physical_submitted": student.physical_submitted,
                "plagiarism_checked": student.plagiarism_checked,
                "annotation_submitted": student.annotation_submitted,
                "call_status": call_status,
                "call_status_label": status_label
            }

            students_by_course[course].append(student_data)
            all_students_with_status.append(student_data)

        sorted_courses = sorted(students_by_course.keys())

        return templates.TemplateResponse(
            "admin_teacher_students.html",
            {
                "request": request,
                "teacher": teacher,
                "students_by_course": students_by_course,
                "students": all_students_with_status,  # Добавляем общий список для статистики
                "sorted_courses": sorted_courses,
                "current_user": user,
                "total_students": total_students
            }
        )

    finally:
        db.close()


# Модели для архивных работ
class ArchivedWorkCreate(BaseModel):
    student_id: int
    academic_year: str
    work_type: str
    course: int
    title: str
    topic: Optional[str] = None
    supervisor_name: Optional[str] = None
    pdf_submitted: Optional[bool] = False
    physical_submitted: Optional[bool] = False
    grade: Optional[str] = None
    comments: Optional[str] = None
    plagiarism_checked: Optional[bool] = False
    annotation_submitted: Optional[bool] = False
    submission_date: Optional[str] = None
    defense_date: Optional[str] = None


class ArchivedWorkUpdate(BaseModel):
    title: Optional[str] = None
    topic: Optional[str] = None
    supervisor_name: Optional[str] = None
    pdf_submitted: Optional[bool] = None
    physical_submitted: Optional[bool] = None
    grade: Optional[str] = None
    comments: Optional[str] = None
    plagiarism_checked: Optional[bool] = None
    annotation_submitted: Optional[bool] = None


# Страница архива для преподавателя/администратора
@app.get("/archive", response_class=HTMLResponse)
def archive(request: Request):
    user = get_current_user(request)

    if not user or (user.role != "teacher" and user.role != "admin"):
        return RedirectResponse(url="/login")

    db = SessionLocal()

    try:
        teacher_id = None
        if user.role == "teacher":
            teacher = db.query(models.Teacher).filter(models.Teacher.user_id == user.id).first()
            if teacher:
                teacher_id = teacher.id
            else:
                db.close()
                return templates.TemplateResponse(
                    "error.html",
                    {"request": request, "error": "Преподаватель не найден"}
                )

        current_year = datetime.now().year
        current_academic_year = f"{current_year-1}/{current_year}"   # ВОТ ТУТ ГОД!!!!

        if user.role == "admin":
            works = db.query(models.ArchivedWork, models.Student) \
                .join(models.Student, models.ArchivedWork.student_id == models.Student.id) \
                .order_by(models.ArchivedWork.academic_year.desc(),
                          models.ArchivedWork.course,
                          models.Student.full_name) \
                .all()
        else:
            works = db.query(models.ArchivedWork, models.Student) \
                .join(models.Student, models.ArchivedWork.student_id == models.Student.id) \
                .filter(models.Student.advisor_id == teacher_id) \
                .order_by(models.ArchivedWork.academic_year.desc(),
                          models.ArchivedWork.course,
                          models.Student.full_name) \
                .all()

        works_by_year = {}
        years = set()

        for work, student in works:
            year = work.academic_year
            years.add(year)

            if year not in works_by_year:
                works_by_year[year] = []

            works_by_year[year].append({
                "id": work.id,
                "student_id": student.id,
                "student_name": student.full_name,
                "student_course": student.course,
                "academic_year": work.academic_year,
                "work_type": work.work_type,
                "course": work.course,
                "title": work.title,
                "topic": work.topic,
                "supervisor_name": work.supervisor_name,
                "pdf_submitted": work.pdf_submitted,
                "physical_submitted": work.physical_submitted,
                "grade": work.grade,
                "comments": work.comments,
                "plagiarism_checked": work.plagiarism_checked,
                "annotation_submitted": work.annotation_submitted,
                "submission_date": work.submission_date,
                "defense_date": work.defense_date,
                "is_archived": True,
            })

        current_academic_works = []

        if user.role == "admin":
            current_students = db.query(models.Student) \
                .order_by(models.Student.course, models.Student.full_name) \
                .all()
        else:
            current_students = db.query(models.Student) \
                .filter(models.Student.advisor_id == teacher_id) \
                .order_by(models.Student.course, models.Student.full_name) \
                .all()

        for student in current_students:
            work_type = "diploma" if student.course == 4 else "coursework"

            current_academic_works.append({
                "id": f"current-{student.id}",  # ID для текущих работ
                "student_id": student.id,
                "student_name": student.full_name,
                "student_course": student.course,
                "academic_year": current_academic_year,
                "work_type": work_type,
                "course": student.course,
                "title": student.topic or "Работа в процессе",  # Тема как название
                "topic": student.topic,
                "supervisor_name": student.scientific_advisor.full_name if student.scientific_advisor else "—",
                "pdf_submitted": student.pdf_submitted,
                "physical_submitted": student.physical_submitted,
                "grade": None,
                "comments": "Текущая работа",
                "plagiarism_checked": student.plagiarism_checked if student.course == 4 else False,
                "annotation_submitted": student.annotation_submitted if student.course == 4 else False,
                "submission_date": None,
                "defense_date": None,
                "is_archived": False,
                "is_current": True,
            })

        if current_academic_year not in works_by_year:
            works_by_year[current_academic_year] = []

        works_by_year[current_academic_year] = current_academic_works + works_by_year.get(current_academic_year, [])
        years.add(current_academic_year)

        for i in range(6):
            year = f"{current_year - 1-i}/{current_year - i }" #вот тут {current_year -i}/{current_year - i +1} тогда реально текущий
            years.add(year)
            if year not in works_by_year:
                works_by_year[year] = []

        years_list = sorted(list(years), reverse=True)

        if current_academic_year in years_list:
            years_list.remove(current_academic_year)
            years_list.insert(0, current_academic_year)

        if user.role == "admin":
            students_list = db.query(models.Student) \
                .order_by(models.Student.full_name) \
                .all()
        else:
            students_list = db.query(models.Student) \
                .filter(models.Student.advisor_id == teacher_id) \
                .order_by(models.Student.full_name) \
                .all()

        students_for_modal = [
            {"id": s.id, "full_name": s.full_name, "course": s.course}
            for s in students_list
        ]

        academic_years_list = [f"{current_year - i}/{current_year - i + 1}" for i in range(6)]

        db.close()

        return templates.TemplateResponse(
            "archive.html",
            {
                "request": request,
                "current_user": user,
                "years": years_list,
                "works_by_year": works_by_year,
                "students_for_modal": students_for_modal,
                "academic_years": academic_years_list,
                "current_academic_year": current_academic_year,
                "current_year": current_year,
                "range": range,
                "is_admin": user.role == "admin",
                "active_year": None,
            }
        )

    except Exception as e:
        db.close()
        print(f"Error in archive: {e}")
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": str(e)}
        )
# Добавление архивной работы
@app.post("/add-archived-work")
async def add_archived_work(work_data: ArchivedWorkCreate, request: Request):
    user = get_current_user(request)

    if not user or (user.role != "teacher" and user.role != "admin"):
        return {"success": False, "error": "Доступ запрещен"}

    db = SessionLocal()

    try:
        student = db.query(models.Student).filter(models.Student.id == work_data.student_id).first()
        if not student:
            return {"success": False, "error": "Студент не найден"}

        if user.role == "teacher" and student.advisor_id != user.teacher_object.id:
            return {"success": False, "error": "Это не ваш студент"}

        submission_date = None
        defense_date = None

        if work_data.submission_date:
            submission_date = datetime.strptime(work_data.submission_date, "%Y-%m-%d").date()

        if work_data.defense_date:
            defense_date = datetime.strptime(work_data.defense_date, "%Y-%m-%d").date()

        archived_work = models.ArchivedWork(
            student_id=work_data.student_id,
            academic_year=work_data.academic_year,
            work_type=work_data.work_type,
            course=work_data.course,
            title=work_data.title,
            # topic=work_data.topic,
            supervisor_name=work_data.supervisor_name,
            pdf_submitted=work_data.pdf_submitted,
            physical_submitted=work_data.physical_submitted,
            grade=work_data.grade,
            comments=work_data.comments,
            plagiarism_checked=work_data.plagiarism_checked,
            annotation_submitted=work_data.annotation_submitted,
            submission_date=submission_date,
            defense_date=defense_date
        )

        db.add(archived_work)
        db.commit()
        db.refresh(archived_work)

        return {
            "success": True,
            "message": "Архивная работа добавлена",
            "work_id": archived_work.id
        }

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()


# Удаление архивной работы
@app.delete("/delete-archived-work/{work_id}")
async def delete_archived_work(work_id: int, request: Request):
    user = get_current_user(request)

    if not user or (user.role != "teacher" and user.role != "admin"):
        return {"success": False, "error": "Доступ запрещен"}

    db = SessionLocal()

    try:
        work = db.query(models.ArchivedWork).filter(models.ArchivedWork.id == work_id).first()
        if not work:
            return {"success": False, "error": "Работа не найдена"}

        student = work.student
        if user.role == "teacher" and student.advisor_id != user.teacher_object.id:
            return {"success": False, "error": "Это не ваш студент"}

        db.delete(work)
        db.commit()

        return {"success": True, "message": "Работа удалена"}

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()


# Обновление архивной работы
@app.post("/update-archived-work/{work_id}")
async def update_archived_work(work_id: int, work_data: ArchivedWorkUpdate, request: Request):
    user = get_current_user(request)

    if not user or (user.role != "teacher" and user.role != "admin"):
        return {"success": False, "error": "Доступ запрещен"}

    db = SessionLocal()

    try:
        work = db.query(models.ArchivedWork).filter(models.ArchivedWork.id == work_id).first()
        if not work:
            return {"success": False, "error": "Работа не найдена"}

        student = work.student
        if user.role == "teacher" and student.advisor_id != user.teacher_object.id:
            return {"success": False, "error": "Это не ваш студент"}

        if work_data.title is not None:
            work.title = work_data.title

        if work_data.topic is not None:
            work.topic = work_data.topic

        if work_data.supervisor_name is not None:
            work.supervisor_name = work_data.supervisor_name

        if work_data.pdf_submitted is not None:
            work.pdf_submitted = work_data.pdf_submitted

        if work_data.physical_submitted is not None:
            work.physical_submitted = work_data.physical_submitted

        if work_data.grade is not None:
            work.grade = work_data.grade

        if work_data.comments is not None:
            work.comments = work_data.comments

        if work_data.plagiarism_checked is not None:
            work.plagiarism_checked = work_data.plagiarism_checked

        if work_data.annotation_submitted is not None:
            work.annotation_submitted = work_data.annotation_submitted

        work.updated_at = datetime.utcnow()
        db.commit()

        return {"success": True, "message": "Работа обновлена"}

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()



# from datetime import datetime
#
# @app.context_processor
# def utility_processor():
#     return dict(now=datetime.now)

# @app.context_processor
# def utility_processor():
#     def get_current_year():
#         return datetime.now().year
#
#     def get_academic_year(offset=0):
#         """Возвращает учебный год с учетом смещения"""
#         current_year = datetime.now().year
#         return f"{current_year - offset - 1}/{current_year - offset}"
#
#     return {
#         "now": datetime.now,
#         "current_year": get_current_year,
#         "academic_year": get_academic_year,
#         "len": len,  # Добавляем стандартную функцию len
#         "enumerate": enumerate,  # Добавляем enumerate
#         "range": range,  # Добавляем range
#     }

@app.get("/admin/populate-archive")
def admin_populate_archive(request: Request):
    """Заполняет архив тестовыми данными (только для администратора)"""
    user = get_current_user(request)

    if not user or user.role != "admin":
        return {"success": False, "error": "Доступ запрещен"}

    try:
        from populate_archive import populate_archive
        populate_archive()

        return {"success": True, "message": "Архив успешно заполнен"}

    except Exception as e:
        return {"success": False, "error": str(e)}


from pathlib import Path


UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
STUDENT_FILES_DIR = UPLOAD_DIR / "student_files"
STUDENT_FILES_DIR.mkdir(exist_ok=True)


# Модели для работы с файлами
class StudentFileUpload(BaseModel):
    description: Optional[str] = None


class TeacherFileNote(BaseModel):
    file_id: int
    note: str


# # Эндпоинт для загрузки файла студентом
# @app.post("/upload-student-file")
# async def upload_student_file(
#         request: Request,
#         file: UploadFile = File(...),
#         description: str = Form("")
# ):
#     user = get_current_user(request)
#
#     if not user or user.role != "student":
#         return {"success": False, "error": "Только студенты могут загружать файлы"}
#
#     db = SessionLocal()
#
#     try:
#         # Получаем студента
#         student = db.query(models.Student).filter(models.Student.user_id == user.id).first()
#         if not student:
#             return {"success": False, "error": "Студент не найден"}
#
#         # Проверяем тип файла
#         allowed_extensions = ['.pdf', '.zip', '.rar', '.7z', '.tar', '.gz']
#         file_extension = os.path.splitext(file.filename)[1].lower()
#
#         if file_extension not in allowed_extensions:
#             return {
#                 "success": False,
#                 "error": "Недопустимый тип файла. Разрешены: PDF, ZIP, RAR, 7Z, TAR, GZ"
#             }
#
#         # Определяем тип файла
#         if file_extension == '.pdf':
#             file_type = 'pdf'
#         elif file_extension in ['.zip', '.rar', '.7z', '.tar', '.gz']:
#             file_type = 'archive'
#         else:
#             file_type = 'other'
#
#         # Создаем директорию для студента
#         student_dir = STUDENT_FILES_DIR / str(student.id)
#         student_dir.mkdir(exist_ok=True)
#
#         # Генерируем уникальное имя файла
#         timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#         safe_filename = f"{timestamp}_{file.filename}"
#         file_path = student_dir / safe_filename
#
#         # Сохраняем файл
#         content = await file.read()
#         file_size = len(content)
#
#         with open(file_path, "wb") as buffer:
#             buffer.write(content)
#
#         # Создаем запись в БД
#         student_file = models.StudentFile(
#             student_id=student.id,
#             filename=safe_filename,
#             original_filename=file.filename,
#             file_path=str(file_path),
#             file_type=file_type,
#             file_size=file_size,
#             description=description
#         )
#
#         db.add(student_file)
#         db.commit()
#         db.refresh(student_file)
#
#         return {
#             "success": True,
#             "message": "Файл успешно загружен",
#             "file_id": student_file.id,
#             "filename": file.filename,
#             "file_type": file_type
#         }
#
#     except Exception as e:
#         db.rollback()
#         return {"success": False, "error": str(e)}
#     finally:
#         db.close()
#

# Эндпоинт для скачивания файла
@app.get("/download-file/{file_id}")
async def download_file(file_id: int, request: Request):
    user = get_current_user(request)

    if not user:
        return {"success": False, "error": "Требуется авторизация"}

    db = SessionLocal()

    try:
        file_record = db.query(models.StudentFile).filter(models.StudentFile.id == file_id).first()

        if not file_record:
            raise HTTPException(status_code=404, detail="Файл не найден")

        student = db.query(models.Student).filter(models.Student.id == file_record.student_id).first()

        if user.role == "student":
            if student.user_id != user.id:
                raise HTTPException(status_code=403, detail="Доступ запрещен")
        elif user.role == "teacher":
            if student.advisor_id != user.teacher_object.id:
                raise HTTPException(status_code=403, detail="Доступ запрещен")
        elif user.role != "admin":
            raise HTTPException(status_code=403, detail="Доступ запрещен")

        file_path = Path(file_record.file_path)

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Файл не найден на сервере")

        return FileResponse(
            path=file_path,
            filename=file_record.original_filename,
            media_type='application/octet-stream'
        )

    finally:
        db.close()


# Эндпоинт для удаления файла (только для студента)
@app.delete("/delete-student-file/{file_id}")
async def delete_student_file(file_id: int, request: Request):
    user = get_current_user(request)

    if not user or user.role != "student":
        return {"success": False, "error": "Только студенты могут удалять свои файлы"}

    db = SessionLocal()

    try:
        file_record = db.query(models.StudentFile).filter(models.StudentFile.id == file_id).first()

        if not file_record:
            return {"success": False, "error": "Файл не найден"}

        student = db.query(models.Student).filter(models.Student.user_id == user.id).first()
        if not student or file_record.student_id != student.id:
            return {"success": False, "error": "Доступ запрещен"}

        file_path = Path(file_record.file_path)
        if file_path.exists():
            file_path.unlink()

        db.delete(file_record)
        db.commit()

        return {"success": True, "message": "Файл удален"}

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()


# Эндпоинт для добавления заметки преподавателя к файлу
@app.post("/add-file-teacher-note")
async def add_file_teacher_note(
        note_data: TeacherFileNote,
        request: Request
):
    user = get_current_user(request)

    if not user or (user.role != "teacher" and user.role != "admin"):
        return {"success": False, "error": "Только преподаватели могут добавлять заметки"}

    db = SessionLocal()

    try:
        file_record = db.query(models.StudentFile).filter(models.StudentFile.id == note_data.file_id).first()

        if not file_record:
            return {"success": False, "error": "Файл не найден"}

        student = db.query(models.Student).filter(models.Student.id == file_record.student_id).first()

        if user.role == "teacher" and student.advisor_id != user.teacher_object.id:
            return {"success": False, "error": "Это не ваш студент"}

        file_record.teacher_note = note_data.note
        file_record.updated_at = datetime.utcnow()

        db.commit()

        return {
            "success": True,
            "message": "Заметка добавлена",
            "note": note_data.note
        }

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()


# Эндпоинт для получения файлов студента
@app.get("/get-student-files/{student_id}")
async def get_student_files(student_id: int, request: Request):
    user = get_current_user(request)

    if not user:
        return {"success": False, "error": "Требуется авторизация"}

    db = SessionLocal()

    try:
        student = db.query(models.Student).filter(models.Student.id == student_id).first()

        if not student:
            return {"success": False, "error": "Студент не найден"}

        if user.role == "student":
            if student.user_id != user.id:
                return {"success": False, "error": "Доступ запрещен"}
        elif user.role == "teacher":
            if student.advisor_id != user.teacher_object.id:
                return {"success": False, "error": "Доступ запрещен"}
        elif user.role != "admin":
            return {"success": False, "error": "Доступ запрещен"}

        files = db.query(models.StudentFile) \
            .filter(models.StudentFile.student_id == student_id) \
            .order_by(models.StudentFile.created_at.desc()) \
            .all()

        files_list = []
        for f in files:
            files_list.append({
                "id": f.id,
                "original_filename": f.original_filename,
                "filename": f.filename,
                "file_type": f.file_type,
                "file_size": f.file_size,
                "file_size_formatted": format_file_size(f.file_size),
                "description": f.description,
                "teacher_note": f.teacher_note,
                "created_at": f.created_at.strftime("%d.%m.%Y %H:%M"),
                "created_at_iso": f.created_at.isoformat()
            })

        return {
            "success": True,
            "files": files_list
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        db.close()


# Вспомогательная функция для форматирования размера файла
def format_file_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


# Модель для загрузки файла преподавателем
class TeacherFileUpload(BaseModel):
    student_id: int
    description: Optional[str] = None


# Эндпоинт для загрузки файла преподавателем
@app.post("/upload-teacher-file")
async def upload_teacher_file(request: Request):

    form = await request.form()
    student_id = form.get('student_id')
    description = form.get('description', '')
    file = form.get('file')

    user = get_current_user(request)
    if not user:
        return {"success": False, "error": "Требуется авторизация"}

    if not file:
        return {"success": False, "error": "Файл не выбран"}

    # Проверяем размер файла (макс 20MB)
    file_size = 0
    file_content = await file.read()
    file_size = len(file_content)
    if file_size > 20 * 1024 * 1024:  # 20MB
        return {"success": False, "error": "Файл слишком большой. Максимальный размер: 20MB"}

    db = SessionLocal()
    try:
        teacher = db.query(Teacher).filter(Teacher.user_id == user.id).first()
        if not teacher:
            return {"success": False, "error": "Преподаватель не найден"}

        student = db.query(Student).filter(Student.id == student_id).first()
        if not student:
            return {"success": False, "error": "Студент не найден"}

        import os
        from datetime import datetime

        upload_dir = "uploads/teacher_files"
        os.makedirs(upload_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{file.filename}"
        file_path = os.path.join(upload_dir, filename)

        with open(file_path, "wb") as f:
            f.write(file_content)

        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext in ['.pdf']:
            file_type = 'pdf'
        elif file_ext in ['.doc', '.docx', '.odt', '.rtf']:
            file_type = 'document'
        elif file_ext in ['.txt']:
            file_type = 'text'
        else:
            file_type = 'other'
        new_file = TeacherFile(
            student_id=int(student_id),
            teacher_id=teacher.id,
            filename=filename,
            original_filename=file.filename,
            file_path=file_path,
            file_type=file_type,
            file_size=file_size,
            description=description,
            created_at=datetime.utcnow()
        )
        db.add(new_file)
        db.commit()
        db.refresh(new_file)

        teacher_name = user.full_name or "Преподаватель"

        create_notification(
            db=db,
            user_id=student.user_id,
            type="material_added",
            title="Новый материал",
            message=f"{teacher_name}: {file.filename}",
            link="/student-work"
        )

        return {
            "success": True,
            "file_id": new_file.id,
            "filename": file.filename
        }

    except Exception as e:
        db.rollback()
        print(f"Ошибка при загрузке файла: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}
    finally:
        db.close()


@app.post("/upload-student-file")
async def upload_student_file(request: Request):
    form = await request.form()
    description = form.get('description', '')
    file = form.get('file')

    user = get_current_user(request)
    if not user:
        return {"success": False, "error": "Требуется авторизация"}

    if not file:
        return {"success": False, "error": "Файл не выбран"}

    # Проверяем размер файла (макс 50MB для студентов)
    file_size = 0
    file_content = await file.read()
    file_size = len(file_content)
    if file_size > 50 * 1024 * 1024:  # 50MB
        return {"success": False, "error": "Файл слишком большой. Максимальный размер: 50MB"}

    db = SessionLocal()
    try:
        student = db.query(Student).filter(Student.user_id == user.id).first()
        if not student:
            return {"success": False, "error": "Студент не найден"}

        import os
        from datetime import datetime

        upload_dir = "uploads/student_files"
        os.makedirs(upload_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{file.filename}"
        file_path = os.path.join(upload_dir, filename)

        with open(file_path, "wb") as f:
            f.write(file_content)

        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext in ['.pdf']:
            file_type = 'pdf'
        elif file_ext in ['.zip', '.rar', '.7z', '.tar', '.gz']:
            file_type = 'archive'
        else:
            file_type = 'other'

        new_file = StudentFile(
            student_id=student.id,
            filename=filename,
            original_filename=file.filename,
            file_path=file_path,
            file_type=file_type,
            file_size=file_size,
            description=description,
            created_at=datetime.utcnow()
        )
        db.add(new_file)
        db.commit()
        db.refresh(new_file)
        if student.advisor_id:
            teacher = db.query(Teacher).filter(Teacher.id == student.advisor_id).first()
            if teacher and teacher.user_id:
                student_name = student.full_name

                create_notification(
                    db=db,
                    user_id=teacher.user_id,
                    type="file_added",
                    title="Новый файл от студента",
                    message=f"{student_name}: {file.filename}",
                    link=f"/teacher/student/{student.user_id}"
                )

        return {
            "success": True,
            "file_id": new_file.id,
            "filename": file.filename
        }

    except Exception as e:
        db.rollback()
        print(f"Ошибка при загрузке файла: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}
    finally:
        db.close()

@app.get("/get-teacher-files/{student_id}")
async def get_teacher_files(student_id: int, request: Request):
    user = get_current_user(request)

    if not user:
        return {"success": False, "error": "Требуется авторизация"}

    db = SessionLocal()

    try:
        student = db.query(models.Student).filter(models.Student.id == student_id).first()

        if not student:
            return {"success": False, "error": "Студент не найден"}

        if user.role == "student":
            if student.user_id != user.id:
                return {"success": False, "error": "Доступ запрещен"}
        elif user.role == "teacher":
            if student.advisor_id != user.teacher_object.id:
                return {"success": False, "error": "Доступ запрещен"}
        elif user.role != "admin":
            return {"success": False, "error": "Доступ запрещен"}

        files = db.query(models.TeacherFile) \
            .filter(models.TeacherFile.student_id == student_id) \
            .order_by(models.TeacherFile.created_at.desc()) \
            .all()

        files_list = []
        for f in files:
            teacher = db.query(models.Teacher).filter(models.Teacher.id == f.teacher_id).first()
            files_list.append({
                "id": f.id,
                "original_filename": f.original_filename,
                "filename": f.filename,
                "file_type": f.file_type,
                "file_size": f.file_size,
                "file_size_formatted": format_file_size(f.file_size),
                "description": f.description,
                "teacher_name": teacher.full_name if teacher else "Преподаватель",
                "created_at": f.created_at.strftime("%d.%m.%Y %H:%M"),
                "created_at_iso": f.created_at.isoformat()
            })

        return {
            "success": True,
            "files": files_list
        }

    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        db.close()


# Эндпоинт для удаления файла преподавателя
@app.delete("/delete-teacher-file/{file_id}")
async def delete_teacher_file(file_id: int, request: Request):
    user = get_current_user(request)

    if not user or (user.role != "teacher" and user.role != "admin"):
        return {"success": False, "error": "Только преподаватели могут удалять свои файлы"}

    db = SessionLocal()

    try:
        file_record = db.query(models.TeacherFile).filter(models.TeacherFile.id == file_id).first()

        if not file_record:
            return {"success": False, "error": "Файл не найден"}

        if user.role == "teacher":
            teacher = db.query(models.Teacher).filter(models.Teacher.user_id == user.id).first()
            if not teacher or file_record.teacher_id != teacher.id:
                return {"success": False, "error": "Вы не являетесь автором этого файла"}

        file_path = Path(file_record.file_path)
        if file_path.exists():
            file_path.unlink()

        db.delete(file_record)
        db.commit()

        return {"success": True, "message": "Файл удален"}

    except Exception as e:
        db.rollback()
        return {"success": False, "error": str(e)}
    finally:
        db.close()


from fastapi.responses import FileResponse, Response
import csv
import io
import json
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os


# Эндпоинт для экспорта в Excel
@app.get("/admin/export/teachers/excel")
async def export_teachers_excel(request: Request):
    user = get_current_user(request)
    if not user or user.role != "admin":
        return {"success": False, "error": "Доступ запрещен"}

    db = SessionLocal()
    try:
        teachers = db.query(models.Teacher).all()
        teachers_data = []

        for teacher in teachers:
            students = db.query(models.Student).filter(models.Student.advisor_id == teacher.id).all()
            total_students = len(students)
            students_by_course = {2: 0, 3: 0, 4: 0}
            topics_selected = 0
            pdf_submitted = 0
            physical_submitted = 0

            for student in students:
                if student.course in students_by_course:
                    students_by_course[student.course] += 1
                if student.topic:
                    topics_selected += 1
                if student.pdf_submitted:
                    pdf_submitted += 1
                if student.physical_submitted:
                    physical_submitted += 1

            fourth_year_students = [s for s in students if s.course == 4]
            fourth_year_count = len(fourth_year_students)
            fourth_year_plagiarism = sum(1 for s in fourth_year_students if s.plagiarism_checked)
            fourth_year_annotation = sum(1 for s in fourth_year_students if s.annotation_submitted)

            teachers_data.append({
                "full_name": teacher.full_name,
                "total_students": total_students,
                "course_2": students_by_course[2],
                "course_3": students_by_course[3],
                "course_4": students_by_course[4],
                "topics_selected": topics_selected,
                "topics_not_selected": total_students - topics_selected,
                "pdf_submitted": pdf_submitted,
                "physical_submitted": physical_submitted,
                "fourth_year_count": fourth_year_count,
                "fourth_year_plagiarism": fourth_year_plagiarism,
                "fourth_year_annotation": fourth_year_annotation,
                "external_link": teacher.external_link or ""
            })

        import xlsxwriter
        output = io.BytesIO()

        workbook = xlsxwriter.Workbook(output)

        # Форматы
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#4CAF50',
            'color': 'white',
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })

        cell_format = workbook.add_format({
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })

        worksheet1 = workbook.add_worksheet('Общая статистика')

        summary_data = [
            ['Отчет по преподавателям', ''],
            ['Дата экспорта', datetime.now().strftime('%d.%m.%Y %H:%M:%S')],
            [''],
            ['Общая статистика', ''],
            ['Всего преподавателей', len(teachers_data)],
            ['Всего студентов', sum(t['total_students'] for t in teachers_data)],
            ['Выбрали тему', sum(t['topics_selected'] for t in teachers_data)],
            ['Не выбрали тему', sum(t['topics_not_selected'] for t in teachers_data)],
            ['PDF сдан', sum(t['pdf_submitted'] for t in teachers_data)],
            ['Бумажная версия', sum(t['physical_submitted'] for t in teachers_data)],
        ]

        row = 0
        for row_data in summary_data:
            for col, value in enumerate(row_data):
                worksheet1.write(row, col, value, header_format if row < 2 else cell_format)
            row += 1

        worksheet1.set_column('A:B', 30)

        worksheet2 = workbook.add_worksheet('Преподаватели')

        headers = ['Преподаватель', 'Всего', '2 курс', '3 курс', '4 курс',
                   'Темы выбрали', 'Темы не выбрали', 'PDF сдан', 'Бумага',
                   '4 курс (всего)', 'Плагиат', 'Аннотация']

        for col, header in enumerate(headers):
            worksheet2.write(0, col, header, header_format)

        for row, teacher in enumerate(teachers_data, 1):
            worksheet2.write(row, 0, teacher['full_name'], cell_format)
            worksheet2.write(row, 1, teacher['total_students'], cell_format)
            worksheet2.write(row, 2, teacher['course_2'], cell_format)
            worksheet2.write(row, 3, teacher['course_3'], cell_format)
            worksheet2.write(row, 4, teacher['course_4'], cell_format)
            worksheet2.write(row, 5, teacher['topics_selected'], cell_format)
            worksheet2.write(row, 6, teacher['topics_not_selected'], cell_format)
            worksheet2.write(row, 7, teacher['pdf_submitted'], cell_format)
            worksheet2.write(row, 8, teacher['physical_submitted'], cell_format)
            worksheet2.write(row, 9, teacher['fourth_year_count'], cell_format)
            worksheet2.write(row, 10, teacher['fourth_year_plagiarism'], cell_format)
            worksheet2.write(row, 11, teacher['fourth_year_annotation'], cell_format)

        worksheet2.set_column('A:A', 30)
        worksheet2.set_column('B:L', 12)

        workbook.close()
        output.seek(0)

        filename = f"teachers_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        return Response(
            content=output.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    finally:
        db.close()


# Эндпоинт для экспорта в CSV
@app.get("/admin/export/teachers/csv")
async def export_teachers_csv(request: Request):
    user = get_current_user(request)
    if not user or user.role != "admin":
        return {"success": False, "error": "Доступ запрещен"}

    db = SessionLocal()
    try:
        teachers = db.query(models.Teacher).all()

        output = io.StringIO()
        writer = csv.writer(output, delimiter=';', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(['Преподаватель', 'Всего студентов', '2 курс', '3 курс', '4 курс',
                         'Темы выбрали', 'Темы не выбрали', 'PDF сдан', 'Бумажная версия',
                         '4 курс (всего)', 'Плагиат (4 курс)', 'Аннотация (4 курс)'])

        for teacher in teachers:
            students = db.query(models.Student).filter(models.Student.advisor_id == teacher.id).all()
            total_students = len(students)
            students_by_course = {2: 0, 3: 0, 4: 0}
            topics_selected = 0
            pdf_submitted = 0
            physical_submitted = 0

            for student in students:
                if student.course in students_by_course:
                    students_by_course[student.course] += 1
                if student.topic:
                    topics_selected += 1
                if student.pdf_submitted:
                    pdf_submitted += 1
                if student.physical_submitted:
                    physical_submitted += 1

            fourth_year_students = [s for s in students if s.course == 4]
            fourth_year_count = len(fourth_year_students)
            fourth_year_plagiarism = sum(1 for s in fourth_year_students if s.plagiarism_checked)
            fourth_year_annotation = sum(1 for s in fourth_year_students if s.annotation_submitted)

            writer.writerow([
                teacher.full_name,
                total_students,
                students_by_course[2],
                students_by_course[3],
                students_by_course[4],
                topics_selected,
                total_students - topics_selected,
                pdf_submitted,
                physical_submitted,
                fourth_year_count,
                fourth_year_plagiarism,
                fourth_year_annotation
            ])

        writer.writerow([])
        writer.writerow(['ОБЩАЯ СТАТИСТИКА'])
        writer.writerow(['Всего преподавателей:', len(teachers)])

        output.seek(0)

        filename = f"teachers_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        return Response(
            content=output.getvalue().encode('utf-8-sig'),
            media_type="text/csv; charset=utf-8-sig",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    finally:
        db.close()


# Эндпоинт для экспорта в JSON
@app.get("/admin/export/teachers/json")
async def export_teachers_json(request: Request):
    user = get_current_user(request)
    if not user or user.role != "admin":
        return {"success": False, "error": "Доступ запрещен"}

    db = SessionLocal()
    try:
        teachers = db.query(models.Teacher).all()
        teachers_data = []

        for teacher in teachers:
            students = db.query(models.Student).filter(models.Student.advisor_id == teacher.id).all()
            students_data = []

            for student in students:
                students_data.append({
                    "id": student.id,
                    "full_name": student.full_name,
                    "course": student.course,
                    "topic": student.topic,
                    "pdf_submitted": student.pdf_submitted,
                    "physical_submitted": student.physical_submitted,
                    "plagiarism_checked": student.plagiarism_checked,
                    "annotation_submitted": student.annotation_submitted
                })

            teachers_data.append({
                "id": teacher.id,
                "full_name": teacher.full_name,
                "external_link": teacher.external_link,
                "students": students_data,
                "total_students": len(students_data)
            })

        export_data = {
            "export_date": datetime.now().isoformat(),
            "total_teachers": len(teachers_data),
            "total_students": sum(t["total_students"] for t in teachers_data),
            "teachers": teachers_data
        }

        filename = f"teachers_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        return Response(
            content=json.dumps(export_data, ensure_ascii=False, indent=2).encode('utf-8'),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    finally:
        db.close()


# Эндпоинт для экспорта в PDF
@app.get("/admin/export/teachers/pdf")
async def export_teachers_pdf(request: Request):
    user = get_current_user(request)
    if not user or user.role != "admin":
        return {"success": False, "error": "Доступ запрещен"}

    db = SessionLocal()
    try:
        pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=72)

        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(
            name='Russian',
            fontName='DejaVuSans',
            fontSize=10,
            leading=12
        ))
        styles.add(ParagraphStyle(
            name='RussianTitle',
            fontName='DejaVuSans',
            fontSize=16,
            leading=20,
            alignment=1,
            spaceAfter=30
        ))
        styles.add(ParagraphStyle(
            name='RussianHeader',
            fontName='DejaVuSans',
            fontSize=12,
            leading=14,
            alignment=0,
            spaceAfter=12,
            spaceBefore=12
        ))

        elements = []

        # Заголовок
        elements.append(Paragraph('Отчет по преподавателям', styles['RussianTitle']))
        elements.append(
            Paragraph(f'Дата формирования: {datetime.now().strftime("%d.%m.%Y %H:%M:%S")}', styles['Russian']))
        elements.append(Spacer(1, 20))

        teachers = db.query(models.Teacher).all()
        teachers_data = []
        total_students_all = 0

        for teacher in teachers:
            students = db.query(models.Student).filter(models.Student.advisor_id == teacher.id).all()
            total_students = len(students)
            total_students_all += total_students

            students_by_course = {2: 0, 3: 0, 4: 0}
            topics_selected = 0

            for student in students:
                if student.course in students_by_course:
                    students_by_course[student.course] += 1
                if student.topic:
                    topics_selected += 1

            teachers_data.append([
                teacher.full_name,
                str(total_students),
                f"{students_by_course[2]}/{students_by_course[3]}/{students_by_course[4]}",
                f"{topics_selected}/{total_students}",
                f"{round(topics_selected / total_students * 100 if total_students > 0 else 0)}%"
            ])

        elements.append(Paragraph('Общая статистика', styles['RussianHeader']))

        summary_data = [
            ['Всего преподавателей:', str(len(teachers))],
            ['Всего студентов:', str(total_students_all)],
            ['Среднее студентов на преподавателя:',
             f"{round(total_students_all / len(teachers) if teachers else 0, 1)}"]
        ]

        summary_table = Table(summary_data, colWidths=[150, 100])
        summary_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))

        elements.append(summary_table)
        elements.append(Spacer(1, 20))

        elements.append(Paragraph('Список преподавателей', styles['RussianHeader']))

        table_headers = [['Преподаватель', 'Всего', '2/3/4 курс', 'Темы', '%']]
        table_data = table_headers + teachers_data

        teacher_table = Table(table_data, colWidths=[150, 50, 80, 80, 50])
        teacher_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'DejaVuSans'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('BACKGROUND', (0, 0), (-1, 0), colors.blue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))

        elements.append(teacher_table)

        doc.build(elements)
        buffer.seek(0)

        filename = f"teachers_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

        return Response(
            content=buffer.getvalue(),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    finally:
        db.close()


# Эндпоинт для скачивания файлов студента
@app.get("/download-student-file/{file_id}")
async def download_student_file(file_id: int, request: Request):
    user = get_current_user(request)

    if not user:
        return {"success": False, "error": "Требуется авторизация"}

    db = SessionLocal()

    try:
        file_record = db.query(models.StudentFile).filter(models.StudentFile.id == file_id).first()

        if not file_record:
            raise HTTPException(status_code=404, detail="Файл не найден")

        student = db.query(models.Student).filter(models.Student.id == file_record.student_id).first()

        if user.role == "student":
            if student.user_id != user.id:
                raise HTTPException(status_code=403, detail="Доступ запрещен")
        elif user.role == "teacher":
            if student.advisor_id != user.teacher_object.id:
                raise HTTPException(status_code=403, detail="Доступ запрещен")
        elif user.role != "admin":
            raise HTTPException(status_code=403, detail="Доступ запрещен")

        file_path = Path(file_record.file_path)

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Файл не найден на сервере")

        return FileResponse(
            path=file_path,
            filename=file_record.original_filename,
            media_type='application/octet-stream'
        )

    finally:
        db.close()


# Эндпоинт для скачивания файлов преподавателя (рекомендаций)
@app.get("/download-teacher-file/{file_id}")
async def download_teacher_file(file_id: int, request: Request):
    user = get_current_user(request)

    if not user:
        return {"success": False, "error": "Требуется авторизация"}

    db = SessionLocal()

    try:
        file_record = db.query(models.TeacherFile).filter(models.TeacherFile.id == file_id).first()

        if not file_record:
            raise HTTPException(status_code=404, detail="Файл не найден")

        student = db.query(models.Student).filter(models.Student.id == file_record.student_id).first()

        if user.role == "student":
            if student.user_id != user.id:
                raise HTTPException(status_code=403, detail="Доступ запрещен")
        elif user.role == "teacher":
            teacher = db.query(models.Teacher).filter(models.Teacher.user_id == user.id).first()
            if not teacher or (file_record.teacher_id != teacher.id and student.advisor_id != teacher.id):
                raise HTTPException(status_code=403, detail="Доступ запрещен")
        elif user.role != "admin":
            raise HTTPException(status_code=403, detail="Доступ запрещен")

        file_path = Path(file_record.file_path)

        if not file_path.exists():
            raise HTTPException(status_code=404, detail="Файл не найден на сервере")

        return FileResponse(
            path=file_path,
            filename=file_record.original_filename,
            media_type='application/octet-stream'
        )

    finally:
        db.close()


# Общий эндпоинт для обратной совместимости (можно удалить позже)
@app.get("/download-file/{file_id}")
async def download_file_legacy(file_id: int, request: Request):
    """Универсальный эндпоинт для скачивания (определяет тип файла автоматически)"""
    user = get_current_user(request)

    if not user:
        return {"success": False, "error": "Требуется авторизация"}

    db = SessionLocal()

    try:
        file_record = db.query(models.StudentFile).filter(models.StudentFile.id == file_id).first()
        file_type = "student"
        if not file_record:
            file_record = db.query(models.TeacherFile).filter(models.TeacherFile.id == file_id).first()
            file_type = "teacher"

        if not file_record:
            raise HTTPException(status_code=404, detail="Файл не найден")

        if file_type == "student":
            return await download_student_file(file_id, request)
        else:
            return await download_teacher_file(file_id, request)

    finally:
        db.close()


# ========== ЭНДПОИНТЫ ДЛЯ УВЕДОМЛЕНИЙ  ==========

@app.get('/api/notifications/{user_id}')
def get_notifications(request: Request, user_id: int):
    """Получить последние уведомления для пользователя"""
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            db.close()
            return {"success": False, "error": "Пользователь не найден"}

        notifications = db.query(Notification).filter(
            Notification.user_id == user_id
        ).order_by(Notification.created_at.desc()).limit(20).all()

        unread_count = db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).count()

        notifications_list = []
        for n in notifications:
            notifications_list.append({
                "id": str(n.id),
                "type": n.type,
                "title": n.title,
                "message": n.message,
                "link": n.link,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat()
            })

        db.close()

        return {
            "success": True,
            "notifications": notifications_list,
            "unread_count": unread_count
        }

    except Exception as e:
        print(f"Ошибка при получении уведомлений: {e}")
        import traceback
        traceback.print_exc()
        db.close()
        return {"success": False, "error": str(e)}


@app.post('/api/notifications/{notification_id}/read')
def mark_notification_read(notification_id: int):
    """Отметить уведомление как прочитанное"""
    db: Session = SessionLocal()
    try:
        notification = db.query(Notification).filter(Notification.id == notification_id).first()
        if notification:
            notification.is_read = True
            db.commit()
            return {"success": True}
        else:
            return {"success": False, "error": "Уведомление не найдено"}
    except Exception as e:
        print(f"Ошибка при отметке уведомления: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


@app.post('/api/notifications/{user_id}/read-all')
def mark_all_notifications_read(user_id: int):
    """Отметить все уведомления пользователя как прочитанные"""
    db: Session = SessionLocal()
    try:
        db.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).update({"is_read": True})
        db.commit()
        return {"success": True}
    except Exception as e:
        print(f"Ошибка при отметке всех уведомлений: {e}")
        return {"success": False, "error": str(e)}
    finally:
        db.close()


@app.get('/api/notifications/{user_id}/all')
def get_all_notifications(user_id: int, page: int = 1, limit: int = 50):
    """Получить все уведомления для пользователя с пагинацией"""
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            db.close()
            return {"success": False, "error": "Пользователь не найден"}

        # Пагинация
        offset = (page - 1) * limit
        notifications = db.query(Notification).filter(
            Notification.user_id == user_id
        ).order_by(Notification.created_at.desc()).offset(offset).limit(limit).all()

        total = db.query(Notification).filter(Notification.user_id == user_id).count()

        notifications_list = []
        for n in notifications:
            notifications_list.append({
                "id": str(n.id),
                "type": n.type,
                "title": n.title,
                "message": n.message,
                "link": n.link,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat()
            })

        db.close()

        return {
            "success": True,
            "notifications": notifications_list,
            "total": total,
            "page": page,
            "limit": limit
        }

    except Exception as e:
        print(f"Ошибка при получении всех уведомлений: {e}")
        import traceback
        traceback.print_exc()
        db.close()
        return {"success": False, "error": str(e)}