from flask import redirect, render_template,session,request,logging
from app.dbservices import crud
from app import app
from app.machine_learning.watson import watsonhandler
from werkzeug.security import generate_password_hash, check_password_hash
from flask_socketio import SocketIO, join_room
from app.handler import convo_handler
from app.machine_learning.data_extractor import extractor
from app.test_relate import generate_test as gt
from app.candidate_scoring import scoring as sc
from app.machine_learning import pers as pp
import json

db = crud()
cand = {}
counter = 1
hand = convo_handler()
wh = watsonhandler()
socketio = SocketIO(app)
first_round_flag = ''

@app.route('/')
@app.route('/index', methods=['POST', 'GET'])
def index():
    return render_template('index.html')


@app.route('/login', methods=['POST', 'GET'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        session.pop('user_id', None)
        doc = db.search_feature(email, 'login_credentials')
        print(doc)
        if len(doc) == 0:
            error = 'Email not found please sign in'
            return render_template('login.html', error=error)
        else:
            if check_password_hash(doc['password'], password):
                session['user_id'] = email
                doc = db.search_feature(email, 'login_credentials')
                username = doc['username']
                return redirect('interaction/'+str(username))
            else:
                error = "Incorrect login credentials"
                return render_template('login.html', error=error)
    return render_template('login.html')


@app.route('/register', methods=['POST', 'GET'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        repass = request.form['repass']
        doc = db.search_feature(email, "login_credentials")
        if len(doc) != 0:
            error = "The email already exists"
            render_template('register.html', error=error)
        else:
            if password == repass:
                hash = generate_password_hash(password)
                cdict = {'_id': email, 'username': username, 'password': hash,
                         'email': email}
                db.insert_feature(cdict, 'login_credentials')
                result = {'_id': session['user_id'], 'username': username, 'first_round_flag':'','test_link_share':''}
                db.insert_feature(result, 'candidate_features')
                return redirect('/login')
    return render_template('register.html')



@app.route('/interaction/<string:username>',methods =['POST','GET'])
def interaction(username):
    assistant = wh.get_assistant()
    id = wh.get_session_id(assistant)
    print(id+"SEE HERE SESSION ID")
    botintro = "Hi!! I'm REBOS, I'll be taking you through the recruitment process and help you clarify your queries."
    return render_template('interaction.html', username=username, session_id=id,
                           botintro=botintro)


@app.route('/evaluation', methods = ['POST','GET'])
def eval():
    score = 0
    questions = session.get('question_dict',None)
    for i in range(len(questions)):
        try:
            q1 = request.form[f'q{i+1}']
        except:
            continue
        if q1 == questions[i]['answer']:
            score += 1
    final_score = sc.totalscoring(session['user_id'])
    if final_score > 1500:
        result = {'_id': session['user_id']}
        flag = 'Pass'
        db.insert_feature(result, 'hr_question')
    else:
        result = {'_id': session['user_id']}
        flag = 'Fail'
        db.insert_feature(result, 'hr_question')

    print("SEEE THE SCORE HERE",str(score),str(final_score))
    print(flag)
    assistant = wh.get_assistant()
    id = wh.get_session_id(assistant)
    rek = db.search_feature(session['user_id'], 'login_credentials')
    username = rek['username']
    context = {
               "skills": {
                   "main skill": {
                       "user_defined": {
                           "flag": 1,
                           "second_round_flag": flag,
                           "username": username
                       }
                   }
               }
            }

    response, contextvariable = wh.watson_request(id, assistant,
                                                    'hr', context)
    response = response['response']
    return render_template('interaction2.html', response = response , session_id =id, username = username)


@app.route('/test', methods=['POST', 'GET'])
def testing():
    k = 1
    questions = gt.gettest(session['user_id'])
    print(questions)
    for i in questions:
        for key, value in i.items():
            if key == 'question_number':
                i[key] = k
                k += 1
    session['question_dict'] = questions

    return render_template('tests.html', questions = questions)


@app.route('/result', methods=['POST', 'GET'])
def report_generate():
    init_doc = db.search_feature(session['user_id'],'hr_question')
    res_str = ''
    for i in range(len(init_doc)):
        try:
            res_str += '.' + init_doc[f'ans{i}']
        except:
            pass
    res_str = res_str[1:]
    print(res_str)
    insights_dict = pp.get_personality_insights(res_str)
    

@app.route('/logout')
def logout():
    session.pop('user_id')
    return redirect('/index')


@socketio.on('join_room')
def handle_session_joining_event(data):
    print(data['session_id'])
    print("The user " + data['username'] + " is connected to room " +
          data['session_id'])
    join_room(data['session_id'])


@socketio.on('send_message')
def handle_send_message(data):
    print("Sent_User: " + data['username'] + "\nMessage:" + data['message'] +
          "\nSession_id:" + data['session_id'])
    socketio.emit('1st_message',data, room = data['session_id'])
    data1 = hand.server_convo_handler(data, session['user_id'])
    global counter
    counter += 1
    socketio.emit('recieve_message', data1, room=data['session_id'])

@socketio.on('send_message2')
def handle_send_message(data):
    print("Sent_User: " + data['username'] + "\nMessage:" + data['message'] +
          "\nSession_id:" + data['session_id'])
    socketio.emit('1st_message',data, room = data['session_id'])
    data1 = hand.second_conversation(data, session['user_id'])
    print("Inside msg2")
    global counter
    counter += 1
    socketio.emit('recieve_message', data1, room=data['session_id'])
