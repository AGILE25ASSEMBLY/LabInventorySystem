from flask import Flask, render_template, request, redirect, url_for, Response, send_file
import pandas as pd
import cv2
from pyzbar.pyzbar import decode
from datetime import datetime
from io import BytesIO
import logging


app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Session variables
df = None
present_ids = []
pc_counter = 0
selected_lab = None

@app.route('/', methods=['GET', 'POST'])
def index():
    global df, present_ids, pc_counter, selected_lab

    if request.method == 'POST':
        dept = request.form.get('department')
        selected_lab = request.form.get('lab')
        file = request.files.get('masterfile')

        if not file:
            return "Error: No file uploaded.", 400

        # Load Excel
        df_all = pd.read_excel(file)
        if dept:
            df = df_all[df_all['Department'] == dept].copy()
        else:
            df = df_all.copy()

        # Init attendance fields
        df['PC_no'] = ''
        df['Attendance'] = 'Absent'
        df['Timestamp'] = ''
        df['Availability'] = 'Yes'

        # Reset session state
        present_ids = []
        pc_counter = 0

        return redirect(url_for('scan'))

    return render_template('index.html')


@app.route('/scan')
def scan():
    if df is None:
        return redirect(url_for('index'))
    return render_template('scan.html', lab_name=selected_lab)


def gen_frames():
    global df, present_ids, pc_counter

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        logging.error("Could not open webcam")
        raise RuntimeError("Could not open webcam")

    while True:
        ret, frame = cap.read()
        if not ret:
            logging.warning("Failed to read frame from webcam")
            break

        # Decode barcode
        for barcode in decode(frame):
            student_id = barcode.data.decode('utf-8')
            logging.info(f"Scanned student ID: {student_id}")

            if student_id in present_ids:
                logging.info(f"Student ID {student_id} already marked present.")
                continue

            match = df[df['ID_number'] == student_id]
            if not match.empty:
                logging.info(f"Match found for student ID {student_id}.")
                present_ids.append(student_id)
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                pc_counter += 1
                if pc_counter <= 60:
                    df.loc[df['ID_number'] == student_id, 'PC_no'] = pc_counter
                    logging.info(f"Assigned PC_no {pc_counter} to student ID {student_id}.")
                df.loc[df['ID_number'] == student_id, 'Attendance'] = 'Present'
                df.loc[df['ID_number'] == student_id, 'Timestamp'] = timestamp
            else:
                logging.warning(f"No match found for student ID {student_id}.")

        # Encode & stream
        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

    cap.release()


@app.route('/video_feed')
def video_feed():
    return Response(gen_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@app.route('/export')
def export():
    if df is None:
        return redirect(url_for('index'))

    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Attendance')
    output.seek(0)

    return send_file(output,
                     download_name='attendance.xlsx',
                     as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


if __name__ == '__main__':
    app.run(debug=True)
