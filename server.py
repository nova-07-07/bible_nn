from flask import Flask, request, jsonify
import os
from flask_cors import CORS
import urllib.parse
import base64
from io import BytesIO
from docx import Document
from docx.image.image import Image

app = Flask(__name__)
CORS(app)


def normalize_path(path):
    if not path:
        return None
    # Decode URL-encoded characters like %20
    path = urllib.parse.unquote(path)
    # Replace backslashes with forward slashes
    path = path.replace("\\", "/")
    return path

def traverse(directory, file_extension=None):
    items = []
    try:
        entries = sorted(os.scandir(directory), key=lambda e: e.name.lower())  # Sort by name (case-insensitive)
        for entry in entries:
            if entry.is_dir():
                sub_items = traverse(entry.path, file_extension)
                if sub_items or file_extension is None:
                    items.append({
                        "name": entry.name,
                        "isfolder": True,
                        "path": entry.path,
                        "items": sub_items
                    })
            elif file_extension is None or entry.name.endswith(file_extension):
                items.append({
                    "name": entry.name,
                    "isfolder": False,
                    "path": entry.path
                })
    except PermissionError:
        return []
    return items


@app.route('/titles', methods=['GET'])
def get_titles():
    backend_path = os.path.join("docs")
    if not os.path.exists(backend_path):
        return jsonify({"error": "Backend folder not found"}), 404

    folder_items = traverse(backend_path)

    return jsonify({
        "name": "backend",
        "isfolder": True,
        "path": backend_path,
        "items": folder_items
    })

BASE_DIR = os.path.abspath(".")

def normalize_path(raw_path):
    if not raw_path:
        return None
    requested_path = os.path.abspath(os.path.join(BASE_DIR, raw_path.strip("/\\")))
    if os.path.commonpath([BASE_DIR, requested_path]) != BASE_DIR:
        return None
    return requested_path

def extract_docx_ordered(path):
    doc = Document(path)
    content = []

    # Map relationship ids to image blobs
    rels = {
        rel.rId: rel.target_part.blob
        for rel in doc.part.rels.values()
        if "image" in rel.reltype
    }

    # Access raw XML of the document
    xml = doc._element
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

    for elem in xml.iter():
        if elem.tag.endswith('}p'):  # Paragraph
            text = ''.join(node.text or '' for node in elem.iter() if node.tag.endswith('}t'))
            if text.strip():
                content.append({'type': 'text', 'data': text})
        elif elem.tag.endswith('}drawing'):  # Image
            blip = elem.find('.//a:blip', namespaces={'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'})
            if blip is not None:
                r_embed = blip.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                if r_embed in rels:
                    blob = rels[r_embed]
                    ext = "png"  # You can determine actual type if needed
                    b64 = base64.b64encode(blob).decode('utf-8')
                    content.append({
                        'type': 'image',
                        'data': f'data:image/{ext};base64,{b64}'
                    })

    return content

@app.route('/content', methods=['GET'])
def get_content():
    raw_path = request.args.get('path')
    file_path = normalize_path(raw_path)

    if not file_path:
        return jsonify({"error": "Missing or invalid 'path' parameter"}), 400
    if not os.path.isfile(file_path):
        return jsonify({"error": "File not found"}), 404

    try:
        if file_path.lower().endswith('.docx'):
            content = extract_docx_ordered(file_path)
            return jsonify({"path": file_path, "content": content})
        else:
            return jsonify({"error": "Only .docx files are supported in this route"}), 415
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
