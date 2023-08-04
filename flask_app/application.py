
"""
Simple flask application to demo model inference
"""

# Loads env variable when running locally
from dotenv import load_dotenv
load_dotenv()

## Add parent directory to path for aws_helpers
import sys
sys.path.append('..')

# Imports
from flask import Flask, request, render_template
import json
import os 
from langchain_inference import run_chain
from feedback import store_feedback
from typing import List
from aws_helpers.rds_tools import execute_and_fetch

### Constants
FACULTIES_PATH = os.path.join('data','documents','faculties.json')
DEV_MODE = 'MODE' in os.environ and os.environ.get('MODE') == 'dev'

### Globals (set upon load)
application = Flask(__name__)
faculties = {}
last_updated_time = None

# Helper functions
def read_text(filename: str, as_json = False):
    result = ''
    with open(filename) as f:
        if as_json: result = json.load(f)
        else: result = f.read()
    return result

def log_question(question: str, context: str, answer: str, reference_ids: List[int]):
    # Save submitted question and answer
    fields = ['question','context','answer','reference_ids']
    data = [question, context, answer, reference_ids]

    payload = json.dumps(dict(zip(fields, data)))
    
    try:
        response = store_feedback(json_payload=payload, logging_only=True)
        print(response)
    except Exception as e:
        # Handle any exceptions that occur during the Lambda invocation
        print(f"ERROR occurs when submitting the feedback to the database: {e}")

def get_last_updated_time():
    """
    Get the last time documents were updated from the RDS table
    Return as a formatted datetime
    """
    sql = """
        SELECT datetime
        FROM update_logs 
        ORDER BY id DESC 
        LIMIT 1"""
    result = execute_and_fetch(sql, dev_mode=DEV_MODE)
    return result[0][0].strftime("%m/%d/%Y, %H:%M:%S (UTC)")
        
@application.route('/', methods=['GET'])
def home():
    # Render the form template
    return render_template('index.html', faculties=faculties, last_updated=last_updated_time)

@application.route('/answer', methods=['POST'])
async def answer():
    # Submission from the form template
    topic = request.form['topic']
    question = request.form['question']
    filter_elems = ['faculty','program','specialization','year']
    program_info = {filter_elem: request.form[filter_elem] for filter_elem in filter_elems if request.form[filter_elem] != ''}
    
    # Checks if the form was submitted with a starting document id
    start_doc = request.args.get('doc')
    if start_doc:
        start_doc = int(start_doc)

    # Run the model inference
    docs, main_response, alerts, removed_docs = await run_chain(program_info,topic,question,start_doc=start_doc)
    
    # Log the question
    context_str = ' : '.join(list(program_info.values()) + [topic])
    log_question(question, context_str, main_response, [doc.metadata['doc_id'] for doc in docs])
    
    # Render the results
    return render_template('ans.html',question=question,context=context_str,docs=docs,
                           form=request.form.to_dict(), main_response=main_response, alerts=alerts,
                           removed_docs=removed_docs, last_updated=last_updated_time)

@application.route('/feedback', methods=['POST'])
async def feedback():
    # Save submitted feedback
    fields = ['feedback-hidden-helpful','feedback-hidden-question','feedback-hidden-context',
              'feedback-hidden-reference-ids','feedback-hidden-response','feedback-reference-select','feedback-comments']
    data = [request.form[field] for field in fields]

    payload = json.dumps(dict(zip(fields, data)))

    try:
        response = store_feedback(json_payload=payload)
        print(response)
    except Exception as e:
        # Handle any exceptions that occur during the Lambda invocation
        print(f"ERROR occurs when submitting the feedback to the database: {e}")
            
    # Render the results
    return render_template('feedback.html')
    
def setup():
    # Upon loading, load the available settings for the form
    global faculties, last_updated_time
    faculties = read_text(FACULTIES_PATH,as_json=True)
    last_updated_time = get_last_updated_time()

setup()

# Run the application
# must be like this to run from container
if __name__ == "__main__":
    application.run(host="0.0.0.0")