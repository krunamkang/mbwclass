# app.py

import firebase_admin
from firebase_admin import credentials, auth, firestore, db
from flask import Flask, render_template, request,redirect, url_for, session, Response, jsonify
import requests
import os
from werkzeug.utils import secure_filename
from flask import send_file
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import fonts
from google.cloud.firestore_v1.base_query import FieldFilter
import random 

app = Flask(__name__)
if os.path.exists("/etc/secrets/serviceAccountKey.json"):
    cred_path = "/etc/secrets/serviceAccountKey.json"
else:
    cred_path = "./etc/secrets/serviceAccountKey.json"

cred = credentials.Certificate(cred_path)  # เปลี่ยน 'on' เป็นที่อยู่ของไฟล์ที่คุณดาวน์โหลด
firebase_admin.initialize_app(cred)
db = firestore.client()

app.secret_key = os.urandom(24)
pdfmetrics.registerFont(TTFont("THSarabunBold", "static/fonts/THSarabunBold.ttf"))


UPLOAD_FOLDER_TASK = 'static/task'
app.config['UPLOAD_FOLDER_TASK'] = UPLOAD_FOLDER_TASK

@app.route("/test1")
def test1():
    return render_template("test1.html")


@app.route('/check_session')
def check_session():
    print('แสดง seension ก่อน')
    print("user id ใน check session ",session.get('user_data', {}).get('firstname'))
    return session.get('user_data', "ไม่พบ session")

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return 'ไม่พบไฟล์'
    
    file = request.files['file']
    if file.filename == '':
        return 'กรุณาเลือกไฟล์'

    filepath = os.path.join(app.config['UPLOAD_FOLDER_TASK'], file.filename)
    file.save(filepath)
    return f'ส่งงานเรียบร้อยแล้ว: {file.filename}'


# กำหนดโฟลเดอร์ปลายทางสำหรับอัปโหลดไฟล์
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ตรวจสอบว่ามีโฟลเดอร์นี้หรือไม่ ถ้าไม่มีให้สร้างขึ้น
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


@app.route("/show_student", methods=["POST"])
def show_student():
    lesson = request.form.get("lesson")
    topic = request.form.get("subtopic")
    class_name = request.form.get("classroom")
    print("toppic คือ ",topic)
    print("lesson คือ ",lesson)
    users_ref = db.collection("users")
    query = users_ref.where("std_class", "==", class_name)
    docs = query.stream()
    # ค้นหานักเรียน
    students = []
    for doc in docs:
        data = doc.to_dict()

        work_doc_ref = users_ref.document(doc.id).collection("score").document("task").collection(lesson).document(topic)
        work_doc = work_doc_ref.get()
        if work_doc.exists:
            work_link = work_doc.to_dict().get("work", None)
        else:
            work_link = None

        students.append({
            "std_number": data.get("std_number", ""),
            "firstname": data.get("firstname", ""),
            "lastname": data.get("lastname", ""),
            "work_link": work_link,
            "score": ""
        })

    return render_template(
        "form_score.html",
        lesson=lesson,
        topic=topic,
        class_name=class_name,
        students=students
    )

@app.route("/add_score_admin", methods=["POST"])
def add_score_admin():
    lesson = request.form.get("lesson")
    topic = request.form.get("topic")
    subject = request.form.get("subject")
    class_name = request.form.get("class_name")

    # คะแนนมาจากฟอร์มเป็น list
    std_numbers = request.form.getlist("std_number")
    scores = request.form.getlist("score")

    for no, sc in zip(std_numbers, scores):
        students_ref = db.collection("users").where("std_class", "==", class_name).where("std_number", "==", no)
        for doc_snap in students_ref.get():
            doc_id = doc_snap.id
            db.collection("users").document(doc_id).collection("scores").document('task').collection(lesson).document(topic).set({
    
                "score": int(sc) if sc else None
            })

    return "บันทึกคะแนนเรียบร้อย"




@app.route('/add_score', methods=['POST'])
def add_score():
   
    user_id = session.get('user_data', {}).get('student_id')  # ดึง user_id จาก session
    print("user id ",user_id)
    if not user_id:
        return "User not logged in", 403
    
    lesson_name = request.form.get('lesson_name')
    lesson_id = request.form.get('lesson_id')
    state = request.form.get('state')
    print(lesson_name,lesson_id)
    try:
        # ดึงข้อมูลคำถามและคำตอบที่ถูกต้องจาก Firestore
        questions_ref = db.collection(lesson_name).document(lesson_id).collection('question')  # อ้างอิงไปยัง collection "questions"
        questions_docs = questions_ref.stream()  # ดึงเอกสารทั้งหมดใน collection
        
        # สร้างพจนานุกรมเก็บคำตอบที่ถูกต้อง
        correct_answers = {}
        for doc in questions_docs:
            data = doc.to_dict()  # แปลงเอกสารเป็น dictionary
            correct_answers[doc.id] = data.get('answer')  # ดึงคำตอบที่ถูกต้อง
            print("คำตอบคือ",data.get('answer'))

        # รับคำตอบจากฟอร์ม
        submitted_answers = request.form.to_dict()
        score = 0

        # คำนวณคะแนน
        for question_id, correct_answer in correct_answers.items():
            user_answer = submitted_answers.get(f"answer_{question_id}")  # ชื่อฟิลด์ต้องตรงกับในฟอร์ม
            print("เขาตอบ",user_answer)
            print("answer_{question_id}",question_id)
            if user_answer == correct_answer:
                score += 1  # เพิ่มคะแนนหากคำตอบถูกต้อง
        # อัปเดตคะแนนใน Firestore
        if state=='pre':
            score_add='prescore'

        elif state=='post':
            score_add='postscore'

        elif state=='test':
            score_add='testcore'
        else:
            score = request.form.get('score')
            score_add='task'

        user_ref = db.collection('users').document(user_id).collection('score').document(score_add).collection(lesson_name).document(lesson_id)
        user_ref.set({lesson_id:score})
        print(f"เพิ่มคะแนน post score{score} ให้กับนักเรียน {user_id} สำเร็จ!")


        score_ref = db.collection('users').document(user_id).collection('score').document('postscore').collection(lesson_name).document(lesson_id)
        score_docs = score_ref.get()  # ดึงเอกสารทั้งหมดใน collection
        
       # สร้างพจนานุกรมเก็บคำตอบที่ถูกต้อง
        score_progress=0
        if score_docs.exists:
            data = score_docs.to_dict()  # ✅ แปลงเป็น dictionary ก่อนถึงจะ loop หรือ sum ได้
            score_progress = sum(data.values())  # รวมค่าของ field ทั้งหมด
            print("คะแนนรวมทั้งหมด:",score_progress)
        else:
            print("ไม่พบเอกสาร postscore")

        task_ref= db.collection('users').document(user_id).collection('score').document('task').collection(lesson_name).document(lesson_id) # อ้างอิงไปยัง collection "questions"
        task_docs = task_ref.get()  # ดึงเอกสารทั้งหมดใน collection
        
       # สร้างพจนานุกรมเก็บคำตอบที่ถูกต้อง
        task_progress=0
        if task_docs.exists:
            data = task_docs.to_dict()  # ✅ แปลงเป็น dictionary ก่อนถึงจะ loop หรือ sum ได้
            for v in data.values():
                try:
                    task_progress += int(v)
                except (ValueError, TypeError):
                    pass  # ข้ามค่าที่แปลงไม่ได้

            print("taskทั้งหมด:", task_progress)
        else:
            print("ไม่พบเอกสาร postscore")
            
        total_progress=score_progress+task_progress

        user_doc_ref = db.collection('users').document(user_id)
        user_doc_ref.update({"progress_status": total_progress})

        print("total progress",total_progress)
        updated_user_data = db.collection('users').document(user_id).get().to_dict()
        session['user_data'] = updated_user_data

    except Exception as e:
        print(f"เกิดข้อผิดพลาด: {e}")
        return "เกิดข้อผิดพลาด", 500

    return redirect(url_for('show_comment', option='option2',lesson_name=lesson_name,lesson_id=lesson_id))




@app.route('/showMenu', methods=['GET','POST'])
def showMenu():
    menu = request.args.get('menu')

    return render_template('index.html',menu=menu)  # ส่งกลับไปที่หน้าเดิมหลังจากบันทึกข้อมูล


@app.route('/showTemplat', methods=['GET','POST'])
def showTemplate():
   
    menutopic_name = request.args.get('menutopic_name')
    lesson_name= request.args.get('lesson_name')
    lesson_id= request.args.get('lesson_id')
    subLesson=request.args.get('subLesson')
    


    menu_lesson = []  # สร้าง List เพื่อเก็บข้อมูลแต่ละ Document
    
    # ดึงข้อมูลทั้งหมดจาก Collection โดยไม่ระบุ Document ID
    menu_ref = db.collection(lesson_name)
    
    try:
        menus = menu_ref.stream()
        for doc in menus:
            # แปลงข้อมูลของ Document เป็น Dictionary และเก็บใน List
           
            menu_class = doc.to_dict()
            menu_class['lesson_id'] = doc.id  # เพิ่ม lesson_id ลงในข้อมูล
            print("เมนู class id คือ ", menu_class['lesson_id'])
            menu_lesson.append(menu_class)

        videos_ref = db.collection(lesson_name).document(lesson_id)  # เข้าถึง Document ของ Lesson
        video_data = videos_ref.get().get("video_url") 


    except Exception as e:
        print("เกิดข้อผิดพลาด:", e)

    

    return render_template('index.html',videos=video_data,Show_Lesson=lesson_name,lesson_name=lesson_name,lesson_id=lesson_id,menu=menu_lesson,subLesson=subLesson)  # ส่งข้อมูลเป็น list



@app.route('/showTemplatAdmin', methods=['GET','POST'])
def showTemplateAdmin():
  
    menu_admin= request.args.get('menu_admin')



    if menu_admin=='test':
        return render_template('insertdata.html')
    if menu_admin=='VideoAct':
        return render_template('insertVideoAc.html')
    if menu_admin=='pre-post':
        return render_template('insertTest.html')
    if menu_admin=='subLesson':
        return render_template('insertSub_Lesson.html')
    if menu_admin=='task_score':
        return render_template('insertTaskScore.html')
    



    return render_template('index.html')  # ส่งข้อมูลเป็น list



@app.route('/insert_prepostTest', methods=['POST'])
def insert_prepostTest():
   
    
    question_id = request.form['question_id']
    question_text = request.form['question_text']
    img_question = request.form.get('img_question', '')
    choices = [
        request.form['choice1'],
        request.form['choice2'],
        request.form['choice3'],
        request.form['choice4']
    ]
    img_choices = [
        request.form.get('img_choice1', ''),
        request.form.get('img_choice2', ''),
        request.form.get('img_choice3', ''),
        request.form.get('img_choice4', '')
    ]
    answer = request.form['answer']

    # สร้าง Document ของ Lesson
    lesson_ref = db.collection('test').document(question_id).set({
        "question_text": question_text,
        "img_question": img_question,
        "choices": choices,
        "img_choices": img_choices,
        "answer": answer
    })

    return render_template('prepostTest.html')  # ส่งกลับไปที่หน้า index หลังจากบันทึกข้อมูล

@app.route('/insert_subLesson', methods=['POST'])
def insert_subLesson():
   
    lesson_name = request.form['lesson_name']
    lesson_id = request.form['lesson_id']
    SubLesson = request.form['SubLesson']
    

   

    # บันทึกข้อมูลคำถาม
    lesson_ref = db.collection(lesson_name).document(lesson_id).set({
        "subLesson": SubLesson,
       
    })


    return render_template('insertSub_Lesson.html')  # ส่งกลับไปที่หน้า index หลังจากบันทึกข้อมูล



@app.route('/insert_question_data', methods=['POST'])
def insert_question_data():
   
    lesson_name = request.form['lesson_name']
    lesson_id = request.form['lesson_id']
    question_id = request.form['question_id']
    question_text = request.form['question_text']
    img_question = request.files.get('img_question').filename
    choices = {
        'choice1':request.form['choice1'],
        'choice2':request.form['choice2'],
        'choice3':request.form['choice3'],
        'choice4':request.form['choice4']
    }
    img_choices = {
        'choice1':request.files.get('img_choice1').filename,
        'choice2':request.files.get('img_choice2').filename,
        'choice3':request.files.get('img_choice3').filename,
        'choice4':request.files.get('img_choice4').filename
    }

    selected_choice = request.form.get('selected_choice')
    print( selected_choice)
    answer = selected_choice

    # สร้าง Document ของ Lesson
    lesson_ref = db.collection(lesson_name).document(lesson_id)

    # บันทึกข้อมูลคำถาม
    lesson_ref.collection("question").document(question_id).set({
        "question_text": question_text,
        "img_question": img_question,
        "choices": choices,
        "img_choices": img_choices,
        "answer": answer
    })

    
    # รับไฟล์จากฟอร์ม
    img_files = {
        'img_choice1': request.files.get('img_choice1'),
        'img_choice2': request.files.get('img_choice2'),
        'img_choice3': request.files.get('img_choice3'),
        'img_choice4': request.files.get('img_choice4'),
        'img_question' : request.files.get('img_question', '')
    }

        # เก็บพาธไฟล์ที่อัปโหลด
    saved_files = {}

    for key, file in img_files.items():
        print("เข้าสู่้การ upload file is ",file)
        print("เข้าสู่้การ upload file is ",file.filename)
        if file and file.filename:  # ตรวจสอบว่ามีไฟล์ถูกอัปโหลด
            filename = file.filename
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)  # บันทึกไฟล์ลงโฟลเดอร์
            saved_files[key] = file_path  # บันทึกพาธไฟล์
            print("upload ไฟล์แล้ว")

    return render_template('insertdata.html')  # ส่งกลับไปที่หน้า index หลังจากบันทึกข้อมูล


# insert Test
@app.route('/insert_test', methods=['POST'])
def insert_test():
   
    
    question_id = request.form['question_id']
    question_text = request.form['question_text']
    img_question = request.files.get('img_question').filename
    choices = {
        'choice1':request.form['choice1'],
        'choice2':request.form['choice2'],
        'choice3':request.form['choice3'],
        'choice4':request.form['choice4']
    }
    img_choices = {
        'choice1':request.files.get('img_choice1').filename,
        'choice2':request.files.get('img_choice2').filename,
        'choice3':request.files.get('img_choice3').filename,
        'choice4':request.files.get('img_choice4').filename
    }

    selected_choice = request.form.get('selected_choice')
    print( selected_choice)
    answer = selected_choice

    # สร้าง Document ของ Lesson
    db.collection("question").document(question_id).set({
        "question_text": question_text,
        "img_question": img_question,
        "choices": choices,
        "img_choices": img_choices,
        "answer": answer
    })

    
    # รับไฟล์จากฟอร์ม
    img_files = {
        'img_choice1': request.files.get('img_choice1'),
        'img_choice2': request.files.get('img_choice2'),
        'img_choice3': request.files.get('img_choice3'),
        'img_choice4': request.files.get('img_choice4'),
        'img_question' : request.files.get('img_question', '')
    }

        # เก็บพาธไฟล์ที่อัปโหลด
    saved_files = {}

    for key, file in img_files.items():
        print("เข้าสู่้การ upload file is ",file)
        print("เข้าสู่้การ upload file is ",file.filename)
        if file and file.filename:  # ตรวจสอบว่ามีไฟล์ถูกอัปโหลด
            filename = file.filename
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)  # บันทึกไฟล์ลงโฟลเดอร์
            saved_files[key] = file_path  # บันทึกพาธไฟล์
            print("upload ไฟล์แล้ว")

    return render_template('insertTest.html')  # ส่งกลับไปที่หน้า index หลังจากบันทึกข้อมูล

def increment_video_id(current_value):
    return (current_value or 0) + 1

@app.route('/insert_video_data', methods=['POST'])
def insert_video_data():
    print("insert video")
    lesson_name = request.form['lesson_name']
    lesson_id = request.form['lesson_id']
    topic_name = request.form['topic_name']
    video_url = request.form['video_url']
    activity_name = request.form['activity_name']

  
    
    # อัปโหลดไฟล์กิจกรรม
    activity_file = request.files['activity_path']
    activity_filename = secure_filename(activity_file.filename)


    lesson_ref = db.collection(lesson_name).document(lesson_id)
    lesson_ref.update({
      
        "video_name": topic_name,
        "video_url": video_url,
        "activity_name": activity_name,
        "activity_path": activity_filename
    })

    return render_template('insertVideoAc.html')  # ส่งกลับไปที่หน้าเดิมหลังจากบันทึกข้อมูล




@app.route('/show_comment', methods=['GET'])
def show_comment():
    option = request.args.get('option')  # รับค่าจากตัวแปร 'option'
    lesson_name = request.args.get('lesson_name')
    lesson_id = request.args.get('lesson_id')
    subLesson = request.args.get('subLesson')
    print("ค่า option",option)

    menu_lesson = []  # สร้าง List เพื่อเก็บข้อมูลแต่ละ Document
    
    # ดึงข้อมูลทั้งหมดจาก Collection โดยไม่ระบุ Document ID
    menu_ref = db.collection(lesson_name)
    
    
    menu_lesson = []  # สร้าง List เพื่อเก็บข้อมูลแต่ละ Document
    
    # ดึงข้อมูลทั้งหมดจาก Collection โดยไม่ระบุ Document ID
    menu_ref = db.collection(lesson_name)
    
    menus = menu_ref.stream()
    for doc in menus:
            # แปลงข้อมูลของ Document เป็น Dictionary และเก็บใน List
        menu_class = doc.to_dict()
        menu_class['lesson_id'] = doc.id  # เพิ่ม lesson_id ลงในข้อมูล
        print( menu_class['lesson_id'])
        menu_lesson.append(menu_class)
        



    if option == 'option1':
        # ทำบางอย่างสำหรับแบบทดสอบก่อนเรียน
        questions = []
        docs = db.collection(lesson_name).document(lesson_id).collection('question').stream()

        for doc in docs:
    
            question_data = doc.to_dict()
            print("ค่า doc id",doc.id)
            questions.append({
                'id': doc.id,
                'question_text': question_data.get('question_text', 'ไม่มีคำถาม'),
                'img_question': question_data.get('img_question', ''),
                'choices': question_data.get('choices', {}),  # ตรวจสอบให้แน่ใจว่าตั้งค่าเป็น list
                'img_choices': question_data.get('img_choices', {}),  # ตรวจสอบให้แน่ใจว่าตั้งค่าเป็น list
                'answer': question_data.get('answer', '')  # ค่าตั้งต้นเมื่อไม่มีคำตอบ
            })
        videos_ref = db.collection(lesson_name).document(lesson_id)  # เข้าถึง Document ของ Lesson
        video_data = videos_ref.get().get("video_url") 

        # ส่งข้อมูลไปยัง HTML
        return render_template('index.html', questions=questions,option=option,lesson_name=lesson_name,lesson_id=lesson_id,subLesson=subLesson,videos=video_data,menu=menu_lesson)
    
        pass
    elif option == 'option2':
        activity_ref = db.collection(lesson_name).document(lesson_id)  # เข้าถึง Document ของ Lesson
        activity_data = activity_ref.get().get("activity_name") 
        videos_ref = db.collection(lesson_name).document(lesson_id)  # เข้าถึง Document ของ Lesson
        video_data = videos_ref.get().get("video_url") 

        return render_template('index.html', option=option,lesson_name=lesson_name,lesson_id=lesson_id,videos=video_data,activity_data=activity_data,subLesson=subLesson,menu=menu_lesson)

        pass
    elif option == 'option3':
        # ทำบางอย่างสำหรับแบบทดสอบหลังเรียน
        questions = []
        docs = db.collection(lesson_name).document(lesson_id).collection('question').stream()

        for doc in docs:
    
            question_data = doc.to_dict()
            print("ค่า doc id",doc.id)
            questions.append({
                'id': doc.id,
                'question_text': question_data.get('question_text', 'ไม่มีคำถาม'),
                'img_question': question_data.get('img_question', ''),
                'choices': question_data.get('choices', []),  # ตรวจสอบให้แน่ใจว่าตั้งค่าเป็น list
                'img_choices': question_data.get('img_choices', []),  # ตรวจสอบให้แน่ใจว่าตั้งค่าเป็น list
                'answer': question_data.get('answer', '')  # ค่าตั้งต้นเมื่อไม่มีคำตอบ
            })

        random.shuffle(questions)
        videos_ref = db.collection(lesson_name).document(lesson_id)  # เข้าถึง Document ของ Lesson
        video_data = videos_ref.get().get("video_url") 

        # ส่งข้อมูลไปยัง HTML
        return render_template('index.html', questions=questions,option=option,lesson_name=lesson_name,lesson_id=lesson_id,videos=video_data,subLesson=subLesson,menu=menu_lesson)


        pass
    elif option == 'option4':
        # ดึงความคิดเห็นจาก Firestore
        comments_ref = db.collection(lesson_name).document(lesson_id).collection('video_comment').order_by('timestamp', direction=firestore.Query.DESCENDING).stream()        
        comment_list = [comment.to_dict() for comment in comments_ref]  # ใช้ to_dict() ที่นี่    


        videos_ref = db.collection(lesson_name).document(lesson_id)  # เข้าถึง Document ของ Lesson
        video_data = videos_ref.get().get("video_url") 

        return render_template('index.html',comments=comment_list,option=option,lesson_name=lesson_name,lesson_id=lesson_id,videos=video_data,subLesson=subLesson,menu=menu_lesson)
        pass
    
    return render_template('index.html',option=option,lesson_name=lesson_name,lesson_id=lesson_id,subLesson=subLesson,menu=menu_lesson)


@app.route('/submit_comment', methods=['POST','GET'])
def submit_comment(): 
    lesson_name=request.form.get('lesson_name')
    lesson_id=request.form.get('lesson_id')
 
    if request.method == 'POST':
        comment = request.form['comment']
        print(f"Received comment: {comment}")
        student_id = session.get('user_data', {}).get('firstname') # หรือข้อมูลผู้ใช้ที่คุณต้องการ user_data['firstname']
        print("student id คือ",student_id)
        #video_id = "1"  # เปลี่ยนเป็น ID ของวิดีโอที่เกี่ยวข้อง



        # บันทึกความคิดเห็นใน Firestore
        db.collection(lesson_name).document(lesson_id).collection('video_comment').add({
            'comment': comment,
            'user_id': student_id,
           # 'video_id': video_id,
            'timestamp': firestore.SERVER_TIMESTAMP
        })
      
        


        return redirect(url_for('show_comment', option='option4',lesson_name=lesson_name,lesson_id=lesson_id))



def register_user(email, password,title ,firstname ,lastname,student_id, std_class, std_number,progress_status):
    existing_email = db.collection('users').where(filter=FieldFilter('email', '==', email)).get()
    print("register p1")
    if existing_email:
        print("email =",email)
        return False 
    # เก็บข้อมูลผู้ใช้ใน Firestoreprint("inshow comment")
    existing_user = db.collection('users').document(student_id).get()
    if existing_user.exists:
        return False  # รหัสซ้ำredirect(url_for('show_comment', option='option2',lesson_name=lesson_name,lesson_id=lesson_id))
    else:
        print("register p2")
        try:
            user = auth.create_user(
                email=email,
                password=password
            )
            print(f'Successfully created new user: {user.uid}')

            user_data = {

                'email': email,
                'password': password,
                'title': title,
                'firstname': firstname,
                'lastname': lastname,
                'student_id': student_id,
                'std_class': std_class,
                'std_number': std_number,
                'progress_status':progress_status,
                'user_status':'student'
            
            }
            db.collection('users').document(student_id).set(user_data)
            
        except Exception as e:
            print('Error creating new user:', e)
            return False
    
    return True
@app.route('/', methods=['GET', 'POST'])
def home():

    nav='หน้าแรก'
    menu='first'
    return render_template('index.html',menu=menu,nav=nav)


@app.route('/showMainMenu', methods=['GET', 'POST'])
def showMainMenu():
    menu= request.args.get('menu')
    nav= request.args.get('nav')
    if menu=='preTest':
        questions = []
        docs = db.collection('question').stream()
        print("abc")
        for doc in docs:
            
            question_data = doc.to_dict()
            print("ค่า doc id",doc.id)
            questions.append({
                'id': doc.id,
                'question_text': question_data.get('question_text', 'ไม่มีคำถาม'),
                'img_question': question_data.get('img_question', ''),
                'choices': question_data.get('choices', {}),  # ตรวจสอบให้แน่ใจว่าตั้งค่าเป็น list
                'img_choices': question_data.get('img_choices', {}),  # ตรวจสอบให้แน่ใจว่าตั้งค่าเป็น list
                'answer': question_data.get('answer', '')  # ค่าตั้งต้นเมื่อไม่มีคำตอบ
            })

        # ส่งข้อมูลไปยัง HTML
        return render_template('index.html', questions=questions,nav=nav,menu=menu)

    return render_template('index.html',nav=nav,menu=menu)


def login_with_email_password(email, password):
    print("email คือ ",email)
    print("pass คือ ",password)
    
    url = 'https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=AIzaSyColds4E7pXbJy7PdKXbUQ1C1r1OXHFSAI'
    print("ส่วน 1")
    payload = {
        'email': email,
        'password': password,
        'returnSecureToken': True
    }
    print("ส่วน 2")
    response = requests.post(url, json=payload)
    
    if response.status_code == 200:
        user_data = response.json()
        print('Login successful!')
        print("ส่วน 3")   
        
     
        # ดึงข้อมูลผู้ใช้จาก Firestore
        users_ref = db.collection('users').where(filter=FieldFilter('email', '==', email)).stream()
        print("ส่วน 3.0")
      

        for user in users_ref:
            print("ส่วน 3.1")
            user_info = user.to_dict()
            # เพิ่มข้อมูล user_info ลงใน user_data
            user_data['firstname'] = user_info['firstname']
            user_data['lastname'] = user_info['lastname']
            '''if user_info['user_status']=='student':
                user_data['std_class'] = user_info['std_class']
                user_data['student_id'] = user_info['student_id']
                user_data['progress_status'] = user_info['progress_status']
            user_data['user_status'] = user_info['user_status']'''
            user_data['std_class'] = user_info['std_class']
            user_data['student_id'] = user_info['student_id']
            user_data['progress_status'] = user_info['progress_status']
            user_data['user_status'] = user_info['user_status']
            print("ให้แสดง ",user.id, user.to_dict())
        print("ส่วน 4")          
        return user_data
    else:
        print('Login failed:', response.json())
        return None


@app.route('/logout')
def logout():
    # ลบข้อมูล session
    nav='หน้าแรก'
    session.pop('user_data', None)
    return render_template('index.html',nav=nav)  # redirect ไปยังหน้า home

@app.route('/login', methods=['GET', 'POST'])
def login():
    nav = 'หน้าแรก'
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        if not email or not password:
            print("Email or password is missing.")
            return redirect(f'/login?message=fail&nav={nav}')

        print(f"Trying to login with: {email}, {password}")

        user_data = login_with_email_password(email, password)

        if user_data:
            session['user_data'] = user_data
            check_session()
            
            return redirect(f'/login?message=success&nav={nav}')
        else:
            return redirect(f'/login?message=fail&nav={nav}')
    
    return render_template('index.html', nav=nav)

       

@app.route('/register', methods=['GET', 'POST'])
def register():
    print("in register 1")
    show_register = True
    nav='สมัครสมาชิก'
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        title = request.form['title']
        firstname = request.form['firstname']
        lastname = request.form['lastname']
        student_id = request.form['student_id']
        std_class = request.form['std_class']
        std_number = request.form['std_number']
        progress_status = 0
        print("in register2")
        registration_successful = register_user(email, password, title, firstname, lastname, student_id, std_class, std_number,progress_status)
        print("in register3")
        if registration_successful:
            return redirect('/register?message=success')
        else:
            return redirect('/register?message=fail')
        
    return render_template('index.html',show_register=show_register,nav=nav)

def set_certificate_id(user_id):
    print(user_id)
    user_ref = db.collection('users').document(user_id)

    # ดึงข้อมูลเอกสารของผู้ใช้
    user_doc = user_ref.get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        
        # ดึงค่า cer_id ปัจจุบัน ถ้าไม่มีให้เริ่มต้นเป็น 1
        current_cer_id = user_data.get('certificate_number', 0)
        
        # เพิ่มค่า cer_id ขึ้นทีละ 1
        new_cer_id = current_cer_id + 1
        
        # อัปเดต cer_id ใหม่ใน Firestore
        user_ref.update({'certificate_number': new_cer_id})
    return new_cer_id 


def get_certificate_data():
    # ดึงข้อมูลจาก Firestore
    student_id = session.get('user_data', {}).get('student_id') 
    print(student_id)
    doc_ref = db.collection('users').document(student_id)  # ระบุ document ID ของเกียรติบัตร
    doc = doc_ref.get()
    certificate_number=0
    if doc.exists:
        data = doc.to_dict()
        certificate_number = data.get('certificate_number')
        if certificate_number==None:
            certificate_number = set_certificate_id(student_id)

    return certificate_number

@app.route('/certificate' ,methods=['GET', 'POST'])
def certificate():
    nav=request.args.get('nav')
    certificate_no=get_certificate_data()
    progress_status = session.get('user_data', {}).get('progress_status')
    if progress_status is not None:
        progress_status = int(progress_status)
        return render_template('index.html',certificate_no=certificate_no,progress_status=progress_status,nav=nav,message='success')
    else:
        # กำหนดค่าเริ่มต้นให้ progress_status เป็น 0 หรือค่าที่ต้องการ
        progress_status = 0
        print("test")
        return render_template('index.html',certificate_no=certificate_no,progress_status=progress_status,nav=nav,message='fail')

    


@app.route('/generate_certificate')
def generate_certificate():
    # โหลดภาพเกียรติบัตร
    certificate_image = Image.open("static/images/certificate.png")
    
    # ใช้ ImageDraw เพื่อวาดข้อความ
    draw = ImageDraw.Draw(certificate_image)
    
    # กำหนดฟอนต์และขนาด
    try:
        font = ImageFont.truetype("static/fonts/THSarabunBold.ttf", 90)
    except IOError:
        font = ImageFont.load_default()

    # ข้อความที่จะเพิ่มลงในภาพ
    recipient_name = f"{request.args.get('firstname', '')} {request.args.get('lastname', '')}"
    
    # หาตำแหน่งเพื่อให้ข้อความอยู่ตรงกลาง
    text_bbox = draw.textbbox((0, 0), recipient_name, font=font)
    text_width = text_bbox[2] - text_bbox[0]  # width
    text_height = text_bbox[3] - text_bbox[1]  # height

    # ปรับตำแหน่งให้สูงขึ้นเล็กน้อย
    position = ((certificate_image.width - text_width) // 2, (certificate_image.height - text_height) // 2 - 30)  # ลดค่า Y เล็กน้อย



    # วาดข้อความลงในภาพ
    draw.text(position, recipient_name, font=font, fill="black")
    
    # สร้าง BytesIO object เพื่อส่งไฟล์ภาพผ่าน Flask
    img_io = BytesIO()
    certificate_image.save(img_io, 'PNG')
    img_io.seek(0)

    # ส่งไฟล์ภาพที่มีข้อความ
    return send_file(img_io, mimetype='image/png', as_attachment=True, download_name='certificate_with_name.png')

def get_scores_from_firebase():



    student_id = session.get('user_data', {}).get('student_id') 
    doc_ref = db.collection('users').document(student_id)  # ระบุ document ID ของเกียรติบัตร
    doc = doc_ref.get()
    scores = []
    if doc.exists:
        data = doc.to_dict()
        scores.append({
        "name": data.get("name"),
        "score": data.get("score"),
        "grade": data.get("grade")
        })
 
    return scores


def create_pdf(scores):

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("Student Scores Report")

 # เปลี่ยนฟอนต์เป็น TH Sarabun New
    pdf.setFont("THSarabunBold", 16)

    # หัวข้อรายงาน
    pdf.drawString(100, 750, "รายงานคะแนนนักเรียน")
    pdf.setFont("THSarabunBold", 12)


    # วาดตารางคะแนน
    x, y = 100, 700
    pdf.drawString(x, y, "Name")
    pdf.drawString(x + 200, y, "Score")
    pdf.drawString(x + 300, y, "Grade")
    y -= 20

    for student in scores:
        pdf.drawString(x, y, student["name"])
        pdf.drawString(x + 200, y, str(student["score"]))
        pdf.drawString(x + 300, y, student["grade"])
        y -= 20

    pdf.save()
    buffer.seek(0)
    return buffer


@app.route('/report_pdf')
def report_pdf():
    scores = get_scores_from_firebase()
    create_pdf(scores)
    print("PDF generated: student_scores_report.pdf")
    # สร้าง PDF และจัดการ Response
    pdf_buffer = create_pdf(scores)
    return Response(
        pdf_buffer,
        mimetype='application/pdf',
        headers={'Content-Disposition': 'attachment;filename=student_scores_report.pdf'}
    )





if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # default to 5000 when run locally
    app.run(debug=True, host='0.0.0.0', port=port)





# ตัวอย่างการใช้งาน

