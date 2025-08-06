from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify
import pandas as pd
import cv2
from pyzbar.pyzbar import decode
from datetime import datetime
from io import BytesIO
import logging
import base64
import numpy as np

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# In-memory "database" for the session
session_data = {
    'df': None,
    'present_ids': set(),
    'pc_counter': 0,
    'selected_lab': None
}

@app.route('/', methods=['GET', 'POST'])
def index():
    global session_data

    if request.method == 'POST':
        dept = request.form.get('department')
        session_data['selected_lab'] = request.form.get('lab')
        file = request.files.get('masterfile')

        if not file:
            return "Error: No file uploaded.", 400

        try:
            # Load the uploaded Excel file
            df_all = pd.read_excel(file)
            
            # Filter by department if one is selected
            if dept:
                df = df_all[df_all['Department'] == dept].copy()
            else:
                df = df_all.copy()

            # Initialize attendance columns
            df['PC_no'] = ''
            df['Attendance'] = 'Absent'
            df['Timestamp'] = ''
            df['Availability'] = 'Yes'
            
            # Store dataframe in our session data
            session_data['df'] = df

            # Reset other session variables
            session_data['present_ids'] = set()
            session_data['pc_counter'] = 0

            return redirect(url_for('scan'))

        except Exception as e:
            logging.error(f"Error processing file: {e}")
            return "Error: Could not process the uploaded Excel file. Please ensure it's a valid format.", 400

    return render_template('index.html')


@app.route('/scan')
def scan():
    # If the dataframe isn't loaded, redirect back to the home page
    if session_data.get('df') is None:
        return redirect(url_for('index'))
    return render_template('scan.html', lab_name=session_data.get('selected_lab', ''))


@app.route('/scan_frame', methods=['POST'])
def scan_frame():
    """
    Receives a single frame from the browser, scans it for a barcode, 
    and returns the result.
    """
    global session_data
    df = session_data.get('df')
    if df is None:
        return jsonify({'status': 'error', 'message': 'Session not started. Please upload a file first.'}), 400

    # Get the image data from the POST request
    data = request.json
    if not data or 'image' not in data:
        return jsonify({'status': 'error', 'message': 'No image data received.'}), 400

    # The image is a base64-encoded data URL, like "data:image/jpeg;base64,..."
    # We need to strip the header and decode it
    try:
        header, encoded = data['image'].split(",", 1)
        image_data = base64.b64decode(encoded)
        
        # Convert the image data to a numpy array for OpenCV
        np_arr = np.frombuffer(image_data, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if frame is None:
             return jsonify({'status': 'error', 'message': 'Could not decode image.'}), 400

    except Exception as e:
        logging.error(f"Error decoding image: {e}")
        return jsonify({'status': 'error', 'message': 'Invalid image data.'}), 400

    # Decode the barcode from the image
    barcodes = decode(frame)
    if not barcodes:
        return jsonify({'status': 'no_barcode_found'})

    barcode = barcodes[0] # Process the first barcode found
    student_id = barcode.data.decode('utf-8')
    logging.info(f"Scanned student ID: {student_id}")

    # Check if student is already marked present
    if student_id in session_data['present_ids']:
        logging.info(f"Student ID {student_id} already marked present.")
        return jsonify({'status': 'already_scanned', 'student_id': student_id})

    # Find the student in the dataframe
    match_index = df.index[df['ID_number'] == student_id].tolist()
    if match_index:
        index = match_index[0]
        logging.info(f"Match found for student ID {student_id}.")

        # Update the student's record
        session_data['present_ids'].add(student_id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        session_data['pc_counter'] += 1
        
        if session_data['pc_counter'] <= 60:
            df.loc[index, 'PC_no'] = session_data['pc_counter']
            logging.info(f"Assigned PC_no {session_data['pc_counter']} to student ID {student_id}.")
            
        df.loc[index, 'Attendance'] = 'Present'
        df.loc[index, 'Timestamp'] = timestamp

        # Update the main dataframe in our session data
        session_data['df'] = df

        return jsonify({'status': 'success', 'student_id': student_id, 'name': df.loc[index, 'Name']})
    else:
        logging.warning(f"No match found for student ID {student_id}.")
        return jsonify({'status': 'not_found', 'student_id': student_id})


@app.route('/export')
def export():
    df = session_data.get('df')
    if df is None:
        return redirect(url_for('index'))

    # Create an in-memory Excel file
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Attendance')
    output.seek(0)

    return send_file(output,
                     download_name='attendance.xlsx',
                     as_attachment=True,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


if __name__ == '__main__':
    # Use 0.0.0.0 to make it accessible on your local network
    app.run(host='0.0.0.0', port=5000, debug=True)
