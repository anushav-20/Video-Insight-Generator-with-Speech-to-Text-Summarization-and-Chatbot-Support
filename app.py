from flask import Flask, render_template, url_for, request, redirect, flash, session, jsonify
import sqlite3
import os
import PyPDF2
from docx import Document
import speech_recognition as sr
from googletrans import Translator
from gtts import gTTS
import pygame
from mutagen.mp3 import MP3
import google.generativeai as genai
import tempfile
import threading
import time

# Configure Gemini AI
genai.configure(api_key='AIzaSyCAHyMTfa010JgpLoLaM92f_TwcW2msywI')
gemini_model = genai.GenerativeModel('gemini-2.5-flash')
chat = gemini_model.start_chat(history=[])

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Initialize translator
translator = Translator()

# Database setup
def init_db():
    connection = sqlite3.connect('user_data.db')
    cursor = connection.cursor()
    command = """CREATE TABLE IF NOT EXISTS user(name TEXT, password TEXT, mobile TEXT, email TEXT)"""
    cursor.execute(command)
    connection.commit()
    connection.close()

init_db()

chat_history = []
current_audio_file = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/home')
def home():
    if 'user' not in session:
        return redirect('/')
    return render_template('Video.html')

@app.route('/userlog', methods=['GET', 'POST'])
def userlog():
    if request.method == 'POST':
        connection = sqlite3.connect('user_data.db')
        cursor = connection.cursor()

        name = request.form['name']
        password = request.form['password']

        query = "SELECT name, password FROM user WHERE name = ? AND password = ?"
        cursor.execute(query, (name, password))
        result = cursor.fetchall()

        if len(result) == 0:
            return render_template('index.html', msg='Sorry, Incorrect Credentials Provided, Try Again')
        else:
            session['user'] = name
            return redirect('/dashboard')

    return render_template('index.html')

@app.route('/userreg', methods=['GET', 'POST'])
def userreg():
    if request.method == 'POST':
        connection = sqlite3.connect('user_data.db')
        cursor = connection.cursor()

        name = request.form['name']
        password = request.form['password']
        mobile = request.form['phone']
        email = request.form['email']

        # Check if user already exists
        cursor.execute("SELECT * FROM user WHERE name = ? OR email = ?", (name, email))
        if cursor.fetchone():
            return render_template('index.html', msg='Username or Email already exists')

        cursor.execute("INSERT INTO user VALUES (?, ?, ?, ?)", (name, password, mobile, email))
        connection.commit()
        connection.close()

        return render_template('index.html', msg='Successfully Registered')
    
    return render_template('index.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/')
    return render_template('dashboard.html', username=session['user'])

@app.route('/text_summarization', methods=['GET', 'POST'])
def text_summarization():
    if 'user' not in session:
        return redirect('/')
    
    summary = ""
    translated_summaries = {}
    
    if request.method == 'POST':
        # File upload handling
        if 'file' in request.files and request.files['file'].filename != '':
            file = request.files['file']
            file_extension = file.filename.split('.')[-1].lower()
            
            text = ""
            if file_extension == 'pdf':
                # Extract text from PDF
                pdf_reader = PyPDF2.PdfReader(file)
                for page in pdf_reader.pages:
                    text += page.extract_text()
                    
            elif file_extension in ['doc', 'docx']:
                # Extract text from DOC/DOCX
                doc = Document(file)
                for paragraph in doc.paragraphs:
                    text += paragraph.text + "\n"
                    
            elif file_extension in ['mp3', 'wav']:
                # Extract text from audio
                recognizer = sr.Recognizer()
                with sr.AudioFile(file) as source:
                    audio_data = recognizer.record(source)
                    text = recognizer.recognize_google(audio_data)
            
            # Summarize using Gemini
            if text.strip():
                prompt = f"Please summarize the following text in a concise and meaningful way:\n\n{text}"
                response = gemini_model.generate_content(prompt)
                summary = response.text
                
                # Translate to different languages
                languages = {
                    'kannada': 'kn',
                    'hindi': 'hi', 
                    'telugu': 'te'
                }
                
                for lang_name, lang_code in languages.items():
                    try:
                        translated = translator.translate(summary, dest=lang_code)
                        translated_summaries[lang_name] = translated.text
                    except:
                        translated_summaries[lang_name] = "Translation not available"
        
        elif 'text_input' in request.form and request.form['text_input'].strip():
            text = request.form['text_input']
            prompt = f"Please summarize the following text in a concise and meaningful way:\n\n{text}"
            response = gemini_model.generate_content(prompt)
            summary = response.text
            
            # Translate to different languages
            languages = {
                'kannada': 'kn',
                'hindi': 'hi',
                'telugu': 'te'
            }
            
            for lang_name, lang_code in languages.items():
                try:
                    translated = translator.translate(summary, dest=lang_code)
                    translated_summaries[lang_name] = translated.text
                except:
                    translated_summaries[lang_name] = "Translation not available"
    
    return render_template('text_summarization.html', 
                         summary=summary, 
                         translated_summaries=translated_summaries)

@app.route('/text_to_speech', methods=['POST'])
def text_to_speech():
    global current_audio_file
    
    data = request.get_json()
    text = data.get('text', '')
    language = data.get('language', 'en')
    
    if not text:
        return jsonify({'error': 'No text provided'})
    
    # Map languages to codes
    lang_codes = {
        'english': 'en',
        'kannada': 'kn',
        'hindi': 'hi',
        'telugu': 'te'
    }
    
    lang_code = lang_codes.get(language.lower(), 'en')
    
    try:
        # Create temporary file for audio
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
            tts = gTTS(text=text, lang=lang_code, slow=False)
            tts.save(tmp_file.name)
            current_audio_file = tmp_file.name
        
        # Play audio using pygame
        pygame.mixer.init()
        pygame.mixer.music.load(current_audio_file)
        pygame.mixer.music.play()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/stop_audio', methods=['POST'])
def stop_audio():
    global current_audio_file
    try:
        pygame.mixer.music.stop()
        if current_audio_file and os.path.exists(current_audio_file):
            os.unlink(current_audio_file)
            current_audio_file = None
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    if 'user' not in session:
        return redirect('/')
    
    if request.method == 'POST':
        user_input = request.form['query']
        language = request.form.get('language', 'english')
        
        # Translate input to English for Gemini if needed
        if language != 'english':
            translated_input = translator.translate(user_input, dest='en').text
        else:
            translated_input = user_input
        
        gemini_response = chat.send_message(translated_input)
        summary = gemini_response.text
        
        # Translate response back to selected language if needed
        if language != 'english':
            lang_codes = {
                'kannada': 'kn',
                'hindi': 'hi',
                'telugu': 'te'
            }
            lang_code = lang_codes.get(language, 'en')
            summary = translator.translate(summary, dest=lang_code).text
        
        chat_history.append({
            'user_input': user_input,
            'response': summary,
            'language': language,
            'timestamp': time.strftime('%H:%M:%S')
        })
        
        return render_template('chatbot.html', chat_history=chat_history)
    
    return render_template('chatbot.html', chat_history=chat_history)

@app.route('/detectvideo', methods=['GET', 'POST'])
def detectvideo():
    if 'user' not in session:
        return redirect('/')
        
    if request.method == 'POST':
        file = request.files.get('src')
        query = request.form.get('query')

        if not file:
            return render_template('Video.html', msg="No video file uploaded")

        # Save uploaded video
        upload_path = os.path.join('static', 'inputvideo', file.filename)
        file.save(upload_path)

        # Call your detection logic
        from VIDEO import Recognition
        Recognition(file.filename, query)

        return render_template('Video.html',
                            query=query,
                            inputvideo=f'static/inputvideo/{file.filename}',
                            outputvideo=f'static/outputvideo/{file.filename}')

    return render_template('Video.html')

@app.route('/detectlive', methods=['GET', 'POST'])
def detectlive():
    if 'user' not in session:
        return redirect('/')
        
    if request.method == 'POST':
        query = request.form['query']
        from LIVE import LiveRecognition
        LiveRecognition(query)

        return render_template('Live.html', query=query, outputvideo='static/outputvideo/1.mp4')
    return render_template('Live.html')

@app.route('/viewframes')
def viewframes():
    if 'user' not in session:
        return redirect('/')
        
    unique_frames = []
    for img in os.listdir('static/unique'):
        unique_frames.append(url_for('static', filename='unique/'+img))
    common_frames = []
    for img in os.listdir('static/common'):
        common_frames.append(url_for('static', filename='common/'+img))
    return render_template('viewframes.html', common_frames=common_frames, unique_frames=unique_frames)

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)