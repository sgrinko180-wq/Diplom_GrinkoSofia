from app.database import SessionLocal
from app.models import Student, Teacher

db = SessionLocal()

advisor = Teacher(full_name="Иванов Иван Иванович")
db.add(advisor)
db.commit()
db.refresh(advisor)

students = [
    Student(full_name="Петров Пётр Петрович", course=4, topic=None, scientific_advisor=advisor),
    Student(full_name="Сидорова Анна Сергеевна", course=3, topic="Анализ БД", scientific_advisor=advisor),
    Student(full_name="Кузнецов Максим Олегович", course=4, topic=None, scientific_advisor=advisor),
]

db.add_all(students)
db.commit()
db.close()