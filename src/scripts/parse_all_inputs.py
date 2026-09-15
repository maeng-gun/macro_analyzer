import os
import glob
from datetime import datetime
import pdfplumber

def parse_pdf(file_path):
    text = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
    except Exception as e:
        print(f"Error parsing PDF {file_path}: {e}")
    return text

def parse_text_file(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return ""

def cleanup_old_scratch(today_str):
    scratch_dir = "scratch"
    if not os.path.exists(scratch_dir):
        return
    
    for filename in os.listdir(scratch_dir):
        file_path = os.path.join(scratch_dir, filename)
        if os.path.isfile(file_path):
            # 파일명에 오늘 날짜 문자열이 포함되어 있지 않으면 삭제
            if today_str not in filename:
                try:
                    os.remove(file_path)
                    print(f"Removed old scratch file: {filename}")
                except Exception as e:
                    print(f"Failed to remove {filename}: {e}")

def parse_all_inputs():
    today_str = datetime.now().strftime("%Y%m%d")
    cleanup_old_scratch(today_str)
    
    input_dir = "input_staging"
    if not os.path.exists(input_dir):
        os.makedirs(input_dir, exist_ok=True)
        print(f"Created '{input_dir}' directory.")
        
    all_text = []
    files_to_process = glob.glob(os.path.join(input_dir, "*"))
    
    if not files_to_process:
        print(f"No files found in {input_dir}.")
        return

    for file_path in files_to_process:
        if os.path.isdir(file_path):
            continue
            
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            print(f"Parsing PDF: {file_path}")
            content = parse_pdf(file_path)
            if content.strip():
                all_text.append(f"--- Document: {os.path.basename(file_path)} ---\n{content}\n")
        elif ext in [".txt", ".md"]:
            print(f"Reading text/md: {file_path}")
            content = parse_text_file(file_path)
            if content.strip():
                all_text.append(f"--- Document: {os.path.basename(file_path)} ---\n{content}\n")
        else:
            print(f"Skipping unsupported file: {file_path}")

    today_str = datetime.now().strftime("%Y%m%d")
    output_path = os.path.join("scratch", f"parsed_report_{today_str}.md")
    os.makedirs("scratch", exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n\n".join(all_text))
        
    print(f"Successfully merged {len(all_text)} documents into {output_path}")

if __name__ == "__main__":
    parse_all_inputs()
