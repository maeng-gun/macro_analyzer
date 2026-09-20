import os
import glob
import argparse
import pdfplumber

def convert_pdf_to_md(pdf_path, output_path=None):
    if not output_path:
        base, _ = os.path.splitext(pdf_path)
        output_path = f"{base}.md"
        
    print(f"[PDF] Converting {pdf_path} -> {output_path}...")
    text_content = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                txt = page.extract_text()
                if txt:
                    text_content.append(f"<!-- Page {i+1}/{total_pages} -->\n{txt}")
                    
        if text_content:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"# PDF Report: {os.path.basename(pdf_path)}\n\n")
                f.write("\n\n---\n\n".join(text_content))
            print(f"[PDF] Successfully converted: {output_path} ({len(text_content)} pages)")
            return output_path
        else:
            print(f"[PDF] Warning: No text could be extracted from {pdf_path}")
            return None
    except Exception as e:
        print(f"[PDF] Error extracting {pdf_path}: {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Convert PDF inputs in input_staging to Markdown")
    parser.add_argument("--date", help="Optional target date (YYYY-MM-DD) filter")
    args = parser.parse_args()
    
    input_dir = "input_staging"
    if not os.path.exists(input_dir):
        print(f"Directory {input_dir} does not exist.")
        return
        
    pattern = os.path.join(input_dir, f"*{args.date}*.pdf" if args.date else "*.pdf")
    pdf_files = glob.glob(pattern)
    
    if not pdf_files:
        print(f"[PDF] No matching PDF files found in {input_dir}")
        return
        
    converted = 0
    for pdf_file in pdf_files:
        res = convert_pdf_to_md(pdf_file)
        if res:
            converted += 1
            
    print(f"[PDF] Completed converting {converted}/{len(pdf_files)} PDF file(s).")

if __name__ == "__main__":
    main()
