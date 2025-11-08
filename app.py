from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
import json
from sqlalchemy.orm import joinedload
import qrcode
import io
import base64
from fpdf import FPDF  # pip install fpdf

app = Flask(__name__)
app.secret_key = 'secret123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Farmer Model
class Farmer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    phone = db.Column(db.String(20), unique=True)
    password = db.Column(db.String(200))

# Herb Data Model
class HerbData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey('farmer.id'), nullable=False)
    herb_name = db.Column(db.String(100), nullable=False)
    growth_month = db.Column(db.String(50), nullable=False)
    fertilizer_used = db.Column(db.Boolean, nullable=False)
    fertilizer_details = db.Column(db.String(200), nullable=True)
    harvesting_method = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(300), nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)

    farmer = db.relationship('Farmer', backref='herbs')
    lab_ticket = db.relationship('LabTicket', backref='herb', uselist=False)

# Lab Ticket Model
class LabTicket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.String(50), unique=True)
    herb_id = db.Column(db.Integer, db.ForeignKey('herb_data.id'))
    farmer_id = db.Column(db.Integer, db.ForeignKey('farmer.id'))
    farmer_report = db.Column(db.Text)
    manufacturer_report = db.Column(db.Text)
    final_product_data = db.Column(db.Text)
    qr_code_data = db.Column(db.Text)  # base64 PNG image
    manufacturer_finalized = db.Column(db.Boolean, default=False)

    status = db.Column(db.String(50), default='Pending Review')
    map_link = db.Column(db.String(300))           # farm location map link
    lab_report = db.Column(db.Text)
    lab_name = db.Column(db.String(100))
    lab_location = db.Column(db.String(200))
    lab_map_link = db.Column(db.String(300))       # lab map link

    raw_material_verification = db.Column(db.Text)
    processing_method = db.Column(db.Text)
    quality_checks = db.Column(db.Text)
    packaging_details = db.Column(db.Text)
    storage_conditions = db.Column(db.Text)
    batch_number = db.Column(db.String(100))
    certification_info = db.Column(db.Text)
    manufacturer_notes = db.Column(db.Text)

    farmer = db.relationship('Farmer', backref='tickets')

@app.before_request
def create_db():
    db.create_all()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register_farmer', methods=['GET', 'POST'])
def register_farmer():
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form['phone']
        password = generate_password_hash(request.form['password'])

        if Farmer.query.filter_by(phone=phone).first():
            flash("Farmer already registered. Please login.", "warning")
            return redirect(url_for('login_farmer'))

        new_farmer = Farmer(name=name, phone=phone, password=password)
        db.session.add(new_farmer)
        db.session.commit()

        flash("Registration successful! Please login now.", "success")
        return redirect(url_for('login_farmer'))

    return render_template('farmer_register.html')

@app.route('/login_farmer', methods=['GET', 'POST'])
def login_farmer():
    if request.method == 'POST':
        phone = request.form['phone']
        password = request.form['password']
        farmer = Farmer.query.filter_by(phone=phone).first()

        if farmer and check_password_hash(farmer.password, password):
            session['farmer_id'] = farmer.id
            flash("Login successful!", "success")
            return redirect(url_for('farmer_dashboard'))
        else:
            flash("Invalid credentials. Try again.", "danger")
            return redirect(url_for('login_farmer'))

    return render_template('farmer_login.html')

@app.route('/dashboard', methods=["GET", "POST"])
def farmer_dashboard():
    if 'farmer_id' not in session:
        return redirect(url_for('login_farmer'))

    farmer = db.session.get(Farmer, session['farmer_id'])

    if request.method == 'POST':
        herb_name = request.form['herb_name']
        growth_month = request.form['growth_month']
        fertilizer_used = request.form['fertilizer_used'] == 'yes'
        fertilizer_details = request.form.get('fertilizer_details', '')
        harvesting_method = request.form['harvesting_method']
        location = request.form['location']
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')

        new_herb = HerbData(
            farmer_id=farmer.id,
            herb_name=herb_name,
            growth_month=growth_month,
            fertilizer_used=fertilizer_used,
            fertilizer_details=fertilizer_details if fertilizer_used else None,
            harvesting_method=harvesting_method,
            location=location,
            latitude=float(latitude) if latitude else None,
            longitude=float(longitude) if longitude else None
        )
        db.session.add(new_herb)
        db.session.commit()

        ticket_id = "LAB-" + str(uuid.uuid4())[:8].upper()
        map_link = f"https://www.google.com/maps/search/?api=1&query={latitude},{longitude}" if latitude and longitude else None

        new_ticket = LabTicket(
            ticket_id=ticket_id,
            farmer_id=farmer.id,
            herb=new_herb,
            map_link=map_link
        )
        db.session.add(new_ticket)
        db.session.commit()

        flash(f"Herb added successfully! Lab Ticket ID: {ticket_id}", "success")
        return redirect(url_for('farmer_dashboard'))

    herbs = HerbData.query.filter_by(farmer_id=farmer.id).options(joinedload(HerbData.lab_ticket)).all()

    for herb in herbs:
        if herb.lab_ticket and herb.lab_ticket.farmer_report:
            try:
                herb.lab_ticket.farmer_report_decoded = json.loads(herb.lab_ticket.farmer_report)
            except:
                herb.lab_ticket.farmer_report_decoded = []
        else:
            herb.lab_ticket.farmer_report_decoded = []

    return render_template('farmer_dashboard.html', farmer=farmer, herbs=herbs)

@app.route('/download_report/<ticket_id>')
def download_report(ticket_id):
    ticket = LabTicket.query.filter_by(ticket_id=ticket_id).first()
    if not ticket or not ticket.farmer_report:
        flash("No report available for download.", "warning")
        return redirect(url_for('farmer_dashboard'))

    report_items = json.loads(ticket.farmer_report)

    content = f"Lab Report for Ticket ID: {ticket.ticket_id}\n"
    content += f"Farmer: {ticket.farmer.name}\n"
    content += f"Herb: {ticket.herb.herb_name}\n\nReport Details:\n"
    for idx, item in enumerate(report_items, 1):
        content += f"{idx}. {item}\n"

    response = make_response(content)
    response.headers["Content-Disposition"] = f"attachment; filename=LabReport_{ticket.ticket_id}.txt"
    response.headers["Content-Type"] = "text/plain"
    return response

@app.route('/logout')
def logout_farmer():
    session.pop('farmer_id', None)
    flash("Logged out successfully", "info")
    return redirect(url_for('home'))

@app.route('/lab_dashboard')
def lab_dashboard():
    tickets = LabTicket.query.filter_by(status='Pending Review').all()
    return render_template('lab_dashboard.html', tickets=tickets)

@app.route('/lab_ticket_view/<ticket_id>', methods=['GET', 'POST'])
def lab_ticket_view(ticket_id):
    ticket = LabTicket.query.filter_by(ticket_id=ticket_id).first()
    if not ticket:
        flash("Ticket not found.", "danger")
        return redirect(url_for('lab_dashboard'))

    if request.method == 'POST':
        tests = request.form.getlist('lab_report[]')
        ticket.lab_report = json.dumps(tests)
        if tests:
            ticket.farmer_report = json.dumps([tests[0]])
        else:
            ticket.farmer_report = json.dumps([])

        ticket.lab_location = request.form['lab_location']
        ticket.lab_name = request.form['lab_name']

        lab_lat = request.form.get('lab_latitude')
        lab_lon = request.form.get('lab_longitude')
        if lab_lat and lab_lon:
            ticket.lab_map_link = f"https://www.google.com/maps/search/?api=1&query={float(lab_lat)},{float(lab_lon)}"

        ticket.status = "Reviewed"
        db.session.commit()
        flash("Lab report submitted successfully!", "success")
        return redirect(url_for('lab_dashboard'))

    herb_map_link = None
    if ticket.herb and ticket.herb.latitude and ticket.herb.longitude:
        herb_map_link = f"https://www.google.com/maps/search/?api=1&query={ticket.herb.latitude},{ticket.herb.longitude}"

    return render_template('lab_ticket_view.html', ticket=ticket, herb_map_link=herb_map_link)

@app.route('/manufacturer/ticket/<ticket_id>', methods=['GET', 'POST'])
def manufacturer_ticket_view(ticket_id):
    ticket = LabTicket.query.filter_by(ticket_id=ticket_id).first_or_404()

    if request.method == 'POST':
        ticket.manufacturer_report = request.form.get('manufacturer_report', '')
        ticket.final_product_data = request.form.get('final_product_data', '')

        ticket.raw_material_verification = request.form.get('raw_material_verification', '')
        ticket.processing_method = request.form.get('processing_method', '')
        ticket.quality_checks = request.form.get('quality_checks', '')
        ticket.packaging_details = request.form.get('packaging_details', '')
        ticket.storage_conditions = request.form.get('storage_conditions', '')
        ticket.batch_number = request.form.get('batch_number', '')
        ticket.certification_info = request.form.get('certification_info', '')
        ticket.manufacturer_notes = request.form.get('manufacturer_notes', '')

        ticket.manufacturer_finalized = True

        # Prepare all relevant data for QR code JSON
        qr_content = {
            'ticket_id': ticket.ticket_id,
            'farmer_name': ticket.farmer.name if ticket.farmer else '',
            'farmer_phone': ticket.farmer.phone if ticket.farmer else '',
            'farm_location_map_link': ticket.map_link or '',
            'lab_name': ticket.lab_name or '',
            'lab_location': ticket.lab_location or '',
            'lab_map_link': ticket.lab_map_link or '',
            'manufacturer_processing_method': ticket.processing_method or '',
            'manufacturer_quality_checks': ticket.quality_checks or ''
        }

        qr_json_str = json.dumps(qr_content)

        qr_img = qrcode.make(qr_json_str)
        buffer = io.BytesIO()
        qr_img.save(buffer, format="PNG")
        qr_b64 = base64.b64encode(buffer.getvalue()).decode()
        ticket.qr_code_data = qr_b64

        db.session.commit()
        flash("Manufacturer report finalized and QR code generated.", "success")
        return redirect(url_for('manufacturer_ticket_view', ticket_id=ticket_id))

    return render_template('manufacturer_ticket_view.html', ticket=ticket)

@app.route('/product_scan/<ticket_id>')
def product_scan(ticket_id):
    ticket = LabTicket.query.filter_by(ticket_id=ticket_id).first_or_404()

    qr_data = {}
    if ticket.qr_code_data:
        try:
            qr_data = json.loads(base64.b64decode(ticket.qr_code_data).decode())
        except Exception:
            qr_data = {}

    return render_template('product_scan.html', ticket=ticket, qr_data=qr_data)

@app.route('/product_scan_download/<ticket_id>')
def product_scan_download(ticket_id):
    ticket = LabTicket.query.filter_by(ticket_id=ticket_id).first_or_404()

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(0, 10, f"Product Traceability Report - Ticket ID: {ticket.ticket_id}", ln=True, align='C')
    pdf.ln(10)

    def add_section(title, content):
        if content:
            pdf.set_font(style='B')
            pdf.cell(0, 10, title, ln=True)
            pdf.set_font(style='')
            for line in content.split('\n'):
                pdf.multi_cell(0, 10, line)
            pdf.ln(5)

    add_section("Farmer Information", f"Name: {ticket.farmer.name}\nPhone: {ticket.farmer.phone}\nFarm Location Map: {ticket.map_link or 'N/A'}")
    add_section("Lab Information", f"Lab Name: {ticket.lab_name or 'N/A'}\nLab Location: {ticket.lab_location or 'N/A'}\nLab Map Link: {ticket.lab_map_link or 'N/A'}")
    add_section("Manufacturing Details", "")
    add_section(" - Processing Method", ticket.processing_method or 'N/A')
    add_section(" - Quality Checks", ticket.quality_checks or 'N/A')

    pdf_output = pdf.output(dest='S').encode('latin1')

    return Response(pdf_output, mimetype='application/pdf', headers={
        "Content-Disposition": f"attachment; filename=ProductTraceability_{ticket.ticket_id}.pdf",
        "Content-Length": len(pdf_output)
    })

@app.route('/manufacturer_dashboard')
def manufacturer_dashboard():
    tickets = LabTicket.query.filter(LabTicket.status == 'Reviewed', LabTicket.manufacturer_finalized == False).all()
    return render_template('manufacturer_dashboard.html', tickets=tickets)

@app.route('/blockchain_view')
def blockchain_view():
    return "<h2>Blockchain Ledger (Coming Soon)</h2>"

if __name__ == '__main__':
    app.run(debug=True)
