import gradio as gr
import google.generativeai as genai
import docx
import fitz  
import json
import os
import time
from typing import Dict, Any, List


API_KEY = "YOUR_API_KEY" #replace with your actual Google API key


try:
    if API_KEY == "YOUR_API_KEY":
        raise ValueError("Replace 'YOUR_API_KEY' in the script with your actual key.")
    genai.configure(api_key=API_KEY)
except Exception as e:
    print(f"Error configuring Gemini API: {e}")




def extract_doc(file_path: str):
    """Extracts text content from a .docx file."""
    try:
        doc = docx.Document(file_path)
        full_text = [para.text for para in doc.paragraphs if para.text.strip()]
        return '\n'.join(full_text), None
    except Exception as e:
        return None, f"Error reading .docx file: {e}"

def extract_pdf(file_path: str):
    """Extracts text content from a .pdf file."""
    try:
        doc = fitz.open(file_path)
        full_text = [page.get_text() for page in doc]
        doc.close()
        return '\n'.join(full_text), None
    except Exception as e:
        return None, f"Error reading .pdf file: {e}"

def get_metadata(first_chunk: str, doc_name: str) -> Dict[str, Any]:
    """
    First Pass: Analyzes the first chunk to get the document type and process.
    """
    model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
    prompt = f"""
        You are an AI assistant specializing in ADGM legal documents. 
        From the first chunk of the document '{doc_name}' below, identify the document type and the likely legal process.

        1.  **Document Type:** (e.g., Articles of Association, Board Resolution, Employment Contract, etc.)
        2.  **Legal Process:** (e.g., Company Incorporation, Licensing, Employment, etc.)

        Return ONLY a single, valid JSON object in the following format:
        {{
            "document_type": "string",
            "process": "string"
        }}

        Here is the first chunk:
        ---
        {first_chunk}
        ---
    """
    try:
        request_options = {"timeout": 60}
        response = model.generate_content(prompt, request_options=request_options)
        cleaned_response = response.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_response)
    except Exception as e:
        print(f"Error getting metadata: {e}")
        return {"document_type": "Unknown", "process": "Unknown"}


def doc_issues(doc_text: str, doc_name: str) -> List[Dict[str, Any]]:
    
    model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
    # Used ai for generating better few shot prompts, worked better than mine...
    prompt = f"""
        You are an AI-powered Corporate Agent specializing in Abu Dhabi Global Market (ADGM) jurisdiction.
        Thoroughly analyze the entire legal document named '{doc_name}' provided below. Your task is to identify all potential red flags based on ADGM Companies Regulations 2020.

        Focus on these categories:
        - **Incorrect Jurisdiction:** e.g., "courts of the UAE" instead of "ADGM Courts".
        - **Ambiguous Language:** e.g., "will endeavor to" instead of "shall".
        - **Missing Clauses:** e.g., no dispute resolution or governing law clause.
        - **Formatting Errors:** e.g., placeholders like "[insert name]", typos like "RESOVED".
        - **Non-ADGM Law References:** e.g., citing "UAE Federal Law No. 2 of 2015" without specifying ADGM regulations apply.

        For each issue found, provide a section reference, a clear description, a severity level, and a precise suggestion for a fix.

        Return ONLY a single, valid JSON object containing a list of the issues. The format must be:
        {{
          "issues_found": [
            {{
              "document": "{doc_name}",
              "section": "string (e.g., 'Clause 3.1' or 'General')",
              "issue": "string (Description of the red flag)",
              "severity": "string ('High', 'Medium', or 'Low')",
              "suggestion": "string (Recommendation for fixing the issue)"
            }}
          ]
        }}

        If no issues are found, return an empty list: {{"issues_found": []}}.

        Here is the full document text:
        ---
        {doc_text}
        ---
    """
    try:
        request_options = {"timeout": 180}  
        response = model.generate_content(prompt, request_options=request_options)
        cleaned_response = response.text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(cleaned_response).get("issues_found", [])
    except Exception as e:
        print(f"Error getting document issues: {e}")
        raise ValueError(f"The AI analysis for finding issues failed. Error: {e}")


def analyze_document(file_obj):
    """Main function to orchestrate the two-pass analysis process."""
    if file_obj is None:
        yield None, None, "Please upload a document first."
        return

    original_filename = os.path.basename(file_obj.name)
    file_extension = os.path.splitext(original_filename)[1].lower()
    
    yield None, None, "Step 1/4: Extracting text..."
    
    if file_extension == '.docx':
        doc_text, error = extract_doc(file_obj.name)
    elif file_extension == '.pdf':
        doc_text, error = extract_pdf(file_obj.name)
    else:
        error = "Unsupported file type. Please upload a .docx or .pdf file."
        doc_text = None

    if error:
        yield None, None, error
        return

    if not doc_text:
        yield None, None, "Could not find any text in the document."
        return
    
    first_chunk = " ".join(doc_text.split()[:500]) 

    yield None, None, "Step 2/4: Identifying document type..."
    metadata = get_metadata(first_chunk, original_filename)
    
    yield None, None, "Step 3/4: Scanning document for issues..."
    try:
        issues = doc_issues(doc_text, original_filename)
    except Exception as e:
        yield None, None, str(e)
        return

    yield None, None, "Step 4/4: Compiling final report..."
    
    
    missing_docs = []
    required_docs_count = 0
    if metadata.get("process") == "Company Incorporation":
        required_docs_list = [
            "Articles of Association", "Memorandum of Association", "Board Resolution", 
            "Shareholder Resolution", "Incorporation Application Form", "UBO Declaration Form", 
            "Register of Members and Directors"
        ]
        required_docs_count = len(required_docs_list)
        
        identified_doc_type = metadata.get("document_type")
        if identified_doc_type and any(identified_doc_type.lower() in req_doc.lower() for req_doc in required_docs_list):
            
            doc_to_remove = next((req_doc for req_doc in required_docs_list if identified_doc_type.lower() in req_doc.lower()), None)
            if doc_to_remove:
                required_docs_list.remove(doc_to_remove)
        missing_docs = required_docs_list


    final_report = {
        "process": metadata.get("process", "Unknown"),
        "document_identified": metadata.get("document_type", "Unknown"),
        "documents_uploaded": 1,
        "required_documents": required_docs_count,
        "missing_documents": missing_docs,
        "issues_found": issues
    }

    reviewed_filepath = created_file(final_report, doc_text, original_filename)
    
    yield final_report, reviewed_filepath, "Analysis complete!"


def created_file(analysis_json: Dict[str, Any], original_text: str, original_filename: str) -> str:
    """Creates a temporary text file with the analysis report."""
    file_content = f"ADGM Corporate Agent - Analysis Report\n"
    file_content += f"=========================================\n\n"
    file_content += f"Original File: {original_filename}\n\n"
    file_content += f"--- JSON Summary ---\n"
    file_content += json.dumps(analysis_json, indent=2)
    file_content += f"\n\n--- Detailed Comments ---\n"
    for i, issue in enumerate(analysis_json.get("issues_found", [])):
        file_content += f"\n{i + 1}. Issue in Section: {issue.get('section', 'N/A')}\n"
        file_content += f"   - Issue: {issue.get('issue', 'N/A')}\n"
        file_content += f"   - Severity: {issue.get('severity', 'N/A')}\n"
        file_content += f"   - Suggestion: {issue.get('suggestion', 'N/A')}\n"
    file_content += f"\n\n--- Original Document Text ---\n"
    file_content += original_text
    reviewed_filename = f"Reviewed_{os.path.basename(original_filename).replace('.docx', '.txt').replace('.pdf', '.txt')}"
    with open(reviewed_filename, "w", encoding="utf-8") as f:
        f.write(file_content)
    return reviewed_filename


with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        """
        
        Upload your legal document (.docx or .pdf) for an intelligent compliance review. 
        The agent will identify the legal process, check for missing documents, and flag potential issues.
        """
    )
    
    with gr.Row():
        with gr.Column(scale=1):
            file_input = gr.File(label="Upload Document", file_types=[".docx", ".pdf"])
            analyze_button = gr.Button("Analyze Document", variant="primary")
            status_output = gr.Textbox(label="Status", interactive=False)
        with gr.Column(scale=2):
            gr.Markdown("### Analysis Results")
            json_output = gr.JSON(label="Structured Report")
            file_output = gr.File(label="Download Reviewed Document", interactive=False)

    analyze_button.click(
        fn=analyze_document,
        inputs=[file_input],
        outputs=[json_output, file_output, status_output]
    )

if __name__ == "__main__":
    if API_KEY == "YOUR_API_KEY":
        print("\nWARNING: You have not set your Google API key.")
    
    print("Starting the app...")
    demo.launch()
