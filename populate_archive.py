#!/usr/bin/env python3
import sys
import os
import random
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.database import SessionLocal, engine
from app import models


def get_teacher_id_by_name(db: Session, teacher_name: str):
    """Получает ID преподавателя по имени (по фамилии или полному имени)"""
    if not teacher_name:
        return None

    # Сначала пробуем найти по фамилии
    teacher = db.query(models.Teacher).filter(
        models.Teacher.full_name.like(f"%{teacher_name}%")
    ).first()

    if teacher:
        return teacher.id

    # Если не нашли, пробуем найти по фамилии из вашего списка
    teacher_last_names = {
        "Азаров": "Азаров Никита Андреевич",
        "Атрохов": "Атрохов Кирилл Георгиевич",
        "Щеглова": "Щеглова Наталья Леонидовна",
        "Голубева": "Голубева Лариса Леонидовна",
        "Громак": "Громак Валерий Иванович",
        "Малевич": "Малевич Александр Эрнестович",
        "Красовский": "Красовский Сергей Геннадьевич",
        "Кушнеров": "Кушнеров Александр Викторович",
        "Андреева": "Андреева Елена Андреевна",
        "Лаврова": "Лаврова Ольга Антоновна",
        "Василевич": "Василевич Михаил Николаевич",
        "Жерело": "Жерело Анатолий Владимирович",
        "Рапопорт": "Рапопорт Александр Леонидович",
        "Задорожнюк": "Задорожнюк Анна Олеговна",
        "Козлов": "Козлов Илья Игоревич",
        "Заморникова": "Заморникова Наталья Юрьевна",
        "Рыжкин": "Рыжкин Сергей Николаевич",
        "Макаров": "Макаров Владимир Васильевич",
        "Руденок": "Руденок Павел Иванович",
    }

    if teacher_name in teacher_last_names:
        full_name = teacher_last_names[teacher_name]
        teacher = db.query(models.Teacher).filter(
            models.Teacher.full_name == full_name
        ).first()
        return teacher.id if teacher else None

    return None


def create_archived_work(db: Session, student_data, academic_year, supervisor_override=None):
    """Создает архивную запись о работе студента"""
    # Находим или создаем студента
    student = db.query(models.Student).filter(
        models.Student.full_name == student_data["full_name"]
    ).first()

    if not student:
        print(f"  Создаем студента: {student_data['full_name']}")
        # Находим ID научного руководителя
        advisor_id = get_teacher_id_by_name(db, student_data.get("advisor"))

        # Создаем пользователя
        username = student_data["full_name"].split()[0].lower()
        user_email = f"{username}@student.university.by"
        user = models.User(
            email=user_email,
            hashed_password="fakehashedpassword",
            role="student"
        )
        db.add(user)
        db.flush()

        # Создаем студента
        student = models.Student(
            full_name=student_data["full_name"],
            course=student_data["course"],
            topic=student_data.get("topic"),
            advisor_id=advisor_id,
            user_id=user.id,
            pdf_submitted=False,
            physical_submitted=False,
            plagiarism_checked=False,
            annotation_submitted=False
        )
        db.add(student)
        db.flush()

    # Определяем тип работы
    work_type = "diploma" if student_data["course"] == 4 else "coursework"

    # Определяем руководителя для архивной записи
    supervisor_name = None
    if supervisor_override:
        # Находим полное имя преподавателя
        teacher = db.query(models.Teacher).filter(
            models.Teacher.full_name.like(f"%{supervisor_override}%")
        ).first()
        if teacher:
            supervisor_name = teacher.full_name
    elif student_data.get("advisor"):
        teacher = db.query(models.Teacher).filter(
            models.Teacher.full_name.like(f"%{student_data['advisor']}%")
        ).first()
        if teacher:
            supervisor_name = teacher.full_name

    # Определяем, была ли работа сдана
    # Для 2025/2026 - все работы текущие, статусы из базы данных
    # Для прошлых лет - случайные статусы
    current_year = "2025/2026"
    if academic_year == current_year:
        # Используем актуальные статусы из таблицы студентов
        pdf_submitted = student.pdf_submitted if hasattr(student, 'pdf_submitted') else False
        physical_submitted = student.physical_submitted if hasattr(student, 'physical_submitted') else False
        plagiarism_checked = student.plagiarism_checked if hasattr(student, 'plagiarism_checked') else False
        annotation_submitted = student.annotation_submitted if hasattr(student, 'annotation_submitted') else False
    else:
        # Случайные статусы для архивных работ
        pdf_submitted = random.choice([True, False])
        physical_submitted = random.choice([True, False]) if pdf_submitted else False
        plagiarism_checked = student_data["course"] == 4 and random.choice([True, False])
        annotation_submitted = student_data["course"] == 4 and random.choice([True, False])

    # Определяем оценку (если работа сдана)
    grade = None
    if pdf_submitted and physical_submitted:
        # Распределение оценок: 60% отлично, 30% хорошо, 10% удовлетворительно
        grades = ["10", "9", "8","7", "6", "5"]
        weights = [0.2, 0.2, 0.2,0.2, 0.1, 0.1]
        grade = random.choices(grades, weights=weights, k=1)[0]

    # Генерируем даты
    year = int(academic_year.split('/')[0])

    # Дата сдачи (если работа сдана)
    submission_date = None
    if pdf_submitted:
        # Случайный день в мае-июне указанного года
        submission_date = datetime(year, random.randint(5, 6), random.randint(1, 30)).date()

    # Дата защиты (если работа сдана)
    defense_date = None
    if physical_submitted and student_data["course"] == 4:
        # Для дипломов - защита обычно в июне
        defense_date = datetime(year, 6, random.randint(10, 25)).date()

    # Создаем архивную запись
    archived_work = models.ArchivedWork(
        student_id=student.id,
        academic_year=academic_year,
        work_type=work_type,
        course=student_data["course"],
        title=student_data.get("topic") or f"Работа студента {student_data['full_name']}",
        topic=student_data.get("topic"),
        supervisor_name=supervisor_name,
        pdf_submitted=pdf_submitted,
        physical_submitted=physical_submitted,
        grade=grade,
        comments=f"Работа выполнена в {academic_year} учебном году",
        plagiarism_checked=plagiarism_checked,
        annotation_submitted=annotation_submitted,
        submission_date=submission_date,
        defense_date=defense_date
    )

    db.add(archived_work)
    return archived_work


def populate_archive():
    """Заполняет архив данными за несколько лет"""
    db = SessionLocal()

    try:
        # Проверяем, есть ли уже данные
        existing_count = db.query(models.ArchivedWork).count()
        if existing_count > 0:
            print(f"⚠️  В архиве уже есть {existing_count} работ.")
            response = input("Продолжить? (y/n): ")
            if response.lower() != 'y':
                print("Операция отменена.")
                return

        # Данные за 2025/2026 (текущий год)
        students_2025_2026 = [
            # 2 курс
            (2, "Аксенов Евгений", None, "Азаров"),
            (2, "Бейма Ксения", "Разработка цифрового сервиса для автоматизации психологической практики", "Атрохов"),
            (2, "Богданович Екатерина", "Рефлексивный анализ поединков", "Малевич"),
            (2, "Булгаков Арсений", "Обработка табличных данных в Python", "Азаров"),
            (2, "Ванин Владимир", "Оценка скрытых ценностей участников аукциона через ML", "Азаров"),
            (2, "Воробьёва Анастасия", None, "Красовский"),
            (2, "Гарбузов Артём", None, "Громак"),
            (2, "Горбачевский Илья", None, "Кушнеров"),
            (2, "Дубровская Юлия", "Разработка приложения «Читательский дневник»", "Андреева"),
            (2, "Ефремов Егор", None, None),
            (2, "Зарихта Матвей", None, "Азаров"),
            (2, "Змушко София", None, "Кушнеров"),
            (2, "Киселевич Юлия", None, "Красовский"),
            (2, "Клеймёнов Мирослав", "Математическая модель рыночного равновесия", "Громак"),
            (2, "Коровацкий Александр", "Применение математической статистики в компьютерных играх", "Азаров"),
            (2, "Кошевник Екатерина", None, "Кушнеров"),
            (2, "Кристиневич Егор", "Функция Грина и краевая задача", "Громак"),
            (2, "Крихун Валерия", "Разработка обучающего комплекса по дифференциальным уравнениям", "Азаров"),
            (2, "Курганский Максим", "Дизайн аукционных механизмов", "Атрохов"),
            (2, "Лабор Яна", "Применение моделирования BPMN/UML", "Атрохов"),
            (2, "Малахова Мария", "Математическое моделирование колебательных процессов", "Лаврова"),
            (2, "Марзилович Дмитрий", "Уравнение и полиномы Лежандра", "Громак"),
            (2, "Медведева Анастасия", "Управление роботизированной системой", "Малевич"),
            (2, "Мигун Андрей", "Компьютерное моделирование нежёстких молекул", "Малевич"),
            (2, "Новосад Ян-Август", None, None),
            (2, "Орехво Александр", "Моделирование авиационных систем", "Азаров"),
            (2, "Савинова Полина", None, "Малевич"),
            (2, "Савлук Михаил", None, "Красовский"),
            (2, "Санчук Ксения", None, "Кушнеров"),
            (2, "Саченко Егор", "Имитационная модель управления светофорами", "Лаврова"),
            (2, "Спасов Глеб", "Отображение Пуанкаре и хаос", "Громак"),
            (2, "Сунцов Артемий", None, None),
            (2, "Супрон Илья", None, "Атрохов"),
            (2, "Талатынник Мария", "Бизнес-анализ сервиса или приложения", "Атрохов"),
            (2, "Трошин Егор", None, "Кушнеров"),
            (2, "Федоренко Алексей", None, None),
            (
            2, "Фридрих Кристина", "Математическое моделирование процессов взаимодействия веществ с кровью", "Лаврова"),
            (2, "Хоменко Владислав", "Автоматическая классификация ошибок в текстовых задачах", "Азаров"),
            (2, "Цивако Иван", "Модель инвестиционного портфеля в непрерывном времени", "Громак"),
            (2, "Циркун Денис", None, None),
            (2, "Чернов Матвей", "Проектирование сервиса для онлайн-обучения", "Атрохов"),
            (2, "Шакура Мирослав", None, None),
            (2, "Шанькова Ульяна", None, "Голубева"),
            (2, "Шостко Глеб", None, None),
            (2, "Юренко Егор", "Интерактивное голосовое общение с языковой моделью", "Атрохов"),
            (2, "Юрицын Павел", None, "Кушнеров"),

            # 3 курс
            (3, "Авласова Арина", None, "Василевич"),
            (3, "Азарова Ирина",
             "Построение рекомендательной системы социальной сети на основе пользовательской активности", "Азаров"),
            (3, "Амшей Кирилл", None, None),
            (3, "Афанасенко Григорий", "Построение вероятностных моделей распространения заболевания", "Жерело"),
            (3, "Бабичев Артур", None, None),
            (3, "Баркун Иван", None, "Красовский"),
            (3, "Бебешко Юлия", None, "Кушнеров"),
            (3, "Бейзеров Максим", None, None),
            (3, "Беленков Алексей",
             "Использование машинного обучения для матчинга предложений и запросов на маркетплейсах", "Малевич"),
            (3, "Богомолов Илья", "Javascript-приложение для изучения английского языка", "Атрохов"),
            (3, "Бочкарёв Иван", None, "Красовский"),
            (3, "Буткевич Вирсавия", None, "Рапопорт"),
            (3, "Ванин Андрей", None, "Азаров"),
            (3, "Галицкий Иван", None, "Азаров"),
            (3, "Глушец Антон", None, None),
            (3, "Жук Илья", None, None),
            (3, "Жуковская Виолетта", None, "Громак"),
            (3, "Зинатулин Семён", None, None),
            (3, "Каштальян Полина", None, "Кушнеров"),
            (3, "Клименков Роман", None, "Кушнеров"),
            (3, "Ковалёва Алина", None, "Лаврова"),
            (3, "Колтович Роман", None, "Кушнеров"),
            (3, "Копанева Анастасия", None, "Красовский"),
            (3, "Корзун Владислав", None, "Задорожнюк"),
            (3, "Левицкий Ярослав", None, None),
            (3, "Лосиков Владислав", None, "Красовский"),
            (3, "Лука Мария", None, "Заморникова"),
            (3, "Михайловская Анна", None, "Кушнеров"),
            (3, "Налбандян Артём", None, None),
            (3, "Новикова Валерия", "Продакт-менеджмент и дизайн", "Атрохов"),
            (3, "Орпик Артем", None, "Азаров"),
            (3, "Полегин Александр", None, "Красовский"),
            (3, "Попов Илья", None, "Кушнеров"),
            (3, "Пунько Павел", "Реализация RAG-системы", "Атрохов"),
            (3, "Радюк Иван", None, "Красовский"),
            (3, "Скороженок Марина", "Моделирование термомагнитной конвекции в магнитной жидкости", "Лаврова"),
            (3, "Стадник Никита", None, None),
            (3, "Стешкин Илья", None, None),
            (3, "Томкович Алексей", None, None),
            (3, "Трепачко Ярослав", "Детекция дорожных знаков с помощью компьютерного зрения", "Малевич"),
            (3, "Трухан Елизавета", None, "Малевич"),
            (3, "Федорович Андрей", "Математическое моделирование игры «Каркассон»", "Козлов"),
            (3, "Шило Артём", None, "Кушнеров"),
            (3, "Юхо Анна", None, "Азаров"),
            (3, "Язубец Антон", None, "Голубева"),

            # 4 курс
            (4, "Адамович Дмитрий", "Разработка системы интерактивного сторителлинга на основе генеративных моделей",
             "Азаров"),
            (4, "Алексанов Давид", "Разработка мультимодальной системы визуально-семантической интерпретации объектов",
             "Голубева"),
            (4, "Аникеев Максим",
             "Использование диффузионных моделей для аппроксимации политики агента в обучении с подкреплением",
             "Кушнеров"),
            (4, "Атрушкевич Арсений",
             "Сравнительный анализ методов дообучения моделей трекинга при ограниченном объёме размеченных данных",
             "Голубева"),
            (
            4, "Брызгалов Владимир", "Построение компьютерных моделей для исследования динамических систем", "Щеглова"),
            (4, "Булавская Екатерина", "Оптимизация управления запасами на основе прогнозирования продаж", "Атрохов"),
            (4, "Буценко Софья", "Сравнительный анализ различных подходов к хранению данных", "Рыжкин"),
            (4, "Герасимёнок Дарья", "Модель формирования мнений с упрямыми агентами", "Красовский"),
            (
            4, "Гринько Софья", "Проектирование и реализация веб-сервиса для управления курсовыми работами", "Атрохов"),
            (4, "Добринец Евгений", "Обучение с подкреплением в задачах беспилотного управления автомобилем",
             "Кушнеров"),
            (4, "Елинов Алексей",
             "Бизнес-анализ и механизмы совершенствования системы безналичных расчетов с использованием криптовалют в игорном бизнесе Республики Беларусь",
             "Красовский"),
            (4, "Забугина Екатерина",
             "Бизнес-анализ и проектирование веб-приложения для мониторинга использования контактных линз", "Атрохов"),
            (
            4, "Засмужец Егор", "Реализация модель распознавания жанра песни методами машинного обучения", "Василевич"),
            (4, "Зикрацкий Антон", "Проектирование веб-сервиса «умный кошелёк» для физических лиц", "Андреева"),
            (4, "Конаев Кирилл",
             "Разработка интеллектуальной системы управления личными финансами с использованием методов машинного обучения",
             "Красовский"),
            (4, "Коноплицкая Ирина", "Анализ работы колл-центра на основе имитационного моделирования и оптимизации",
             "Лаврова"),
            (4, "Кочина Валерия", "Компьютерное моделирование гемодинамики в кровеносных сосудах", "Лаврова"),
            (4, "Лавренова Анастасия", "Прогнозирование финансовых рынков на основе фундаментального анализа",
             "Василевич"),
            (4, "Лобачевский Никита",
             "Разработка интеллектуальной системы для автоматизации поддержки сотрудников на базе n8n с использованием RAG",
             "Руденок"),
            (4, "Лукин Евгений",
             "Условия обратимости двумерных полиномиальных автономных систем дифференциальных уравнений", "Руденок"),
            (4, "Ляпич Макар",
             "Разработка системы алгоритмической торговли на основе обучения с подкреплением для финансовых рынков",
             "Василевич"),
            (4, "Панковец Егор", "Методы машинного обучения в решении задачи распознавания аккордов", "Малевич"),
            (4, "Пашкович Филипп", "Моделирование процессов распространения ОРВИ", "Макаров"),
            (4, "Подтероб Анна", "Математическое моделирование тиреоидной функции щитовидной железы", "Громак"),
            (4, "Рабыкин Андрей", "Бизнес-анализ и frontend-разработка приложения для подготовки к тестированию",
             "Щеглова"),
            (4, "Радионова Екатерина", "Математическое моделирование динамики роста опухолей", "Громак"),
            (4, "Середа Артур", "Обучение языковой модели с использованием нейро-дифференциальных уравнений",
             "Задорожнюк"),
            (4, "Смирнов Вадим",
             "Проектирование и реализация базы данных для кафедры университета на основе денормализованной реляционной модели",
             "Рыжкин"),
            (4, "Староселец Андрей", "Мобильное приложение для распознавания аккордов", "Малевич"),
            (4, "Тамкович Кирилл", "Реализация вероятностной системы на основе блокчейн-смарт-контрактов", "Азаров"),
            (4, "Тарасенко Павел", "Нейросетевые методы коррекции текстовых изображений", "Козлов"),
            (4, "Тихомиров Вадим", "Разработка интеллектуальной CRM-системы с AI-ассистентом", "Рапопорт"),
            (4, "Урбанович Дмитрий", "Математическая модель и задача оптимизации игры Каркассон", "Козлов"),
            (4, "Хороща Георгий",
             "Разработка веб-приложения для ведения структурированного дневника с системой гранулярного управления доступом",
             "Рыжкин"),
            (4, "Шатухо Андрей",
             "Характеристические показатели Ляпунова стационарных линейных уравнений с запаздыванием", "Макаров"),
        ]

        print("📚 Заполняем архив курсовых и дипломных работ...")
        print("=" * 60)

        # Список лет для заполнения
        years = [
            ("2025/2026", 1.0, "текущий год"),  # Все студенты
            ("2024/2025", 0.8, "прошлый год"),  # 80% студентов
            ("2023/2024", 0.6, "2 года назад"),  # 60% студентов
            ("2022/2023", 0.4, "3 года назад"),  # 40% студентов
        ]

        total_created = 0

        for academic_year, percentage, description in years:
            print(f"\n {academic_year} ({description})")
            print("-" * 40)
            year_created = 0

            for student_data in students_2025_2026:
                course, name, topic, advisor = student_data

                # Для прошлых лет пропускаем некоторых студентов
                if academic_year != "2025/2026" and random.random() > percentage:
                    continue

                # Для прошлых лет корректируем курс
                year_difference = 2025 - int(academic_year.split('/')[0])
                adjusted_course = max(1, course - year_difference)

                # Пропускаем, если курс стал меньше 1 (студент еще не поступил)
                if adjusted_course < 1:
                    continue

                # Определяем тему для прошлых лет
                adjusted_topic = topic
                if adjusted_course < course and topic:
                    # Для младших курсов темы были проще
                    if adjusted_course == 2:
                        adjusted_topic = f"Введение в тему: {topic.split(':')[-1].strip() if ':' in topic else topic}"
                    elif adjusted_course == 3:
                        adjusted_topic = f"Промежуточное исследование: {topic.split(':')[-1].strip() if ':' in topic else topic}"

                # Определяем руководителя (может меняться для прошлых лет)
                adjusted_advisor = advisor
                if academic_year in ["2022/2023", "2023/2024"] and adjusted_advisor:
                    # 20% шанс, что руководитель был другой раньше
                    if random.random() < 0.2:
                        other_advisors = ["Азаров", "Атрохов", "Громак", "Малевич", "Красовский"]
                        other_advisors = [a for a in other_advisors if a != advisor]
                        if other_advisors:
                            adjusted_advisor = random.choice(other_advisors)

                student_info = {
                    "course": adjusted_course,
                    "full_name": name,
                    "topic": adjusted_topic,
                    "advisor": adjusted_advisor
                }

                try:
                    create_archived_work(db, student_info, academic_year, adjusted_advisor)
                    year_created += 1
                    total_created += 1

                    if year_created <= 3:  # Показываем первые 3 для примера
                        print(f"  ✓ {name} ({adjusted_course} курс)")

                except Exception as e:
                    print(f"  ✗ Ошибка при создании работы для {name}: {e}")
                    continue

            print(f"  Всего добавлено: {year_created} работ")

        db.commit()
        print(f"\n{'=' * 60}")
        print(f"✅ УСПЕШНО! Всего добавлено {total_created} архивных работ")
        print(f"📊 Годы: 2025/2026, 2024/2025, 2023/2024, 2022/2023")

        print(f"\n👨‍🎓 Создаем текущих студентов для 2025/2026...")
        print("-" * 40)

        current_students_created = 0
        for student_data in students_2025_2026:
            course, name, topic, advisor = student_data

            student = db.query(models.Student).filter(models.Student.full_name == name).first()

            if not student:
                advisor_id = get_teacher_id_by_name(db, advisor)

                username = name.split()[0].lower()
                user_email = f"{username}@student.university.by"
                user = models.User(
                    email=user_email,
                    hashed_password="fakehashedpassword",
                    role="student"
                )
                db.add(user)
                db.flush()

                student = models.Student(
                    full_name=name,
                    course=course,
                    topic=topic,
                    advisor_id=advisor_id,
                    user_id=user.id,
                    pdf_submitted=False,
                    physical_submitted=False,
                    plagiarism_checked=False,
                    annotation_submitted=False
                )
                db.add(student)
                current_students_created += 1

                if current_students_created <= 3:
                    print(f"  ✓ Создан: {name} ({course} курс)")

        db.commit()
        print(f"  Всего создано текущих студентов: {current_students_created}")

        print(f"\n СТАТИСТИКА:")
        print(f"  Всего студентов в системе: {db.query(models.Student).count()}")
        print(f"  Всего работ в архиве: {db.query(models.ArchivedWork).count()}")

        print(f"\n  Работ по годам:")
        for academic_year, _, _ in years:
            count = db.query(models.ArchivedWork).filter(
                models.ArchivedWork.academic_year == academic_year
            ).count()
            print(f"    {academic_year}: {count} работ")

    except Exception as e:
        db.rollback()
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    print(" Запуск заполнения архива курсовых и дипломных работ")
    print("=" * 60)

    models.Base.metadata.create_all(bind=engine)

    populate_archive()

    print("\n" + "=" * 60)
    print("🏁 Заполнение архива завершено!")
    print("\nТеперь в системе есть:")
    print("  • 19 преподавателей с реальными ссылками")
    print("  • 100+ студентов всех курсов")
    print("  • Архивные работы за 4 учебных года")
    print("  • Текущие студенты для 2025/2026 года")
    print("\nОткройте /archive в браузере чтобы увидеть результат!")