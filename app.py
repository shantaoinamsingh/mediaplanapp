from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "change-me"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "media_poc.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# -------------------------------------------------------
# HELPER FUNCTION: Unified Data Extractor
# -------------------------------------------------------

def get_request_data():
    """
    Returns JSON body if request is JSON,
    otherwise returns form data as a dict.
    """
    if request.is_json:
        return request.get_json() or {}
    else:
        # request.form is ImmutableMultiDict; convert to plain dict
        return request.form.to_dict() if request.form else {}


# -------------------------------------------------------
# MODELS
# -------------------------------------------------------

class MediaBooking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    campaign_name = db.Column(db.String(200), nullable=False)
    channel = db.Column(db.String(50), nullable=False)
    market = db.Column(db.String(100))
    vendor = db.Column(db.String(100))
    start_date = db.Column(db.String(20))
    end_date = db.Column(db.String(20))
    unit_rate = db.Column(db.Float)
    units = db.Column(db.Integer)
    budget = db.Column(db.Float)
    currency = db.Column(db.String(10))
    status = db.Column(db.String(50), default="PLANNED")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class PurchaseOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    po_number = db.Column(db.String(50), unique=True, nullable=False)
    vendor = db.Column(db.String(100), nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey("media_booking.id"))
    total_amount = db.Column(db.Float)
    currency = db.Column(db.String(10))
    status = db.Column(db.String(50), default="CREATED")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    booking = db.relationship("MediaBooking", backref="purchase_orders")


class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    vendor = db.Column(db.String(100), nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey("media_booking.id"))
    po_id = db.Column(db.Integer, db.ForeignKey("purchase_order.id"))
    amount = db.Column(db.Float)
    tax_amount = db.Column(db.Float)
    currency = db.Column(db.String(10))
    status = db.Column(db.String(50), default="RECEIVED")
    comments = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    booking = db.relationship("MediaBooking", backref="invoices")
    po = db.relationship("PurchaseOrder", backref="invoices")


# -------------------------------------------------------
# ROUTES (UI PAGES)
# -------------------------------------------------------

@app.route("/")
def index():
    stats = {
        "bookings": MediaBooking.query.count(),
        "pos": PurchaseOrder.query.count(),
        "invoices": Invoice.query.count()
    }
    return render_template("index.html", stats=stats)


@app.route("/media-bookings", methods=["GET", "POST"])
def media_bookings():
    if request.method == "POST":
        form = get_request_data()

        booking = MediaBooking(
            campaign_name=form.get("campaign_name"),
            channel=form.get("channel"),
            market=form.get("market"),
            vendor=form.get("vendor"),
            start_date=form.get("start_date"),
            end_date=form.get("end_date"),
            unit_rate=float(form.get("unit_rate") or 0),
            units=int(form.get("units") or 0),
            budget=float(form.get("budget") or 0),
            currency=form.get("currency") or "USD",
            status=form.get("status") or "PLANNED"
        )
        db.session.add(booking)
        db.session.commit()

        if request.is_json:
            return jsonify({
                "id": booking.id,
                "status": booking.status,
                "message": "Media booking created"
            }), 201

        flash("Media booking created successfully.", "success")
        return redirect(url_for("media_bookings"))

    bookings = MediaBooking.query.order_by(MediaBooking.created_at.desc()).all()
    return render_template("media_bookings.html", bookings=bookings)


@app.route("/purchase-orders", methods=["GET", "POST"])
def purchase_orders():
    if request.method == "POST":
        form = get_request_data()

        po_number = form.get("po_number")
        vendor = form.get("vendor")

        # --- VALIDATION: PO number required (Option B) ---
        if not po_number:
            if request.is_json:
                return jsonify({"error": "po_number is required"}), 400
            flash("PO Number is required.", "danger")
            return redirect(url_for("purchase_orders"))

        # Vendor is mandatory because DB has nullable=False
        if not vendor:
            if request.is_json:
                return jsonify({"error": "vendor is required"}), 400
            flash("Vendor is required.", "danger")
            return redirect(url_for("purchase_orders"))

        # --- DUPLICATE CHECK ---
        existing = PurchaseOrder.query.filter_by(po_number=po_number).first()
        if existing:
            if request.is_json:
                return jsonify({"error": "PO number already exists"}), 409
            flash("PO Number already exists. Please enter a different value.", "danger")
            return redirect(url_for("purchase_orders"))

        # Create PO
        po = PurchaseOrder(
            po_number=po_number,
            vendor=vendor,
            booking_id=int(form.get("booking_id") or 0),
            total_amount=float(form.get("total_amount") or 0),
            currency=form.get("currency") or "USD",
            status=form.get("status") or "CREATED"
        )

        db.session.add(po)
        db.session.commit()

        if request.is_json:
            return jsonify({
                "id": po.id,
                "po_number": po.po_number,
                "status": po.status,
                "message": "Purchase order created"
            }), 201

        flash("Purchase order created successfully.", "success")
        return redirect(url_for("purchase_orders"))

    pos = PurchaseOrder.query.order_by(PurchaseOrder.created_at.desc()).all()
    bookings = MediaBooking.query.all()
    return render_template("purchase_orders.html", pos=pos, bookings=bookings)


@app.route("/invoices", methods=["GET", "POST"])
def invoices():
    if request.method == "POST":
        form = get_request_data()

        inv = Invoice(
            invoice_number=form.get("invoice_number"),
            vendor=form.get("vendor"),
            booking_id=int(form.get("booking_id") or 0),
            po_id=int(form.get("po_id") or 0),
            amount=float(form.get("amount") or 0),
            tax_amount=float(form.get("tax_amount") or 0),
            currency=form.get("currency") or "USD",
            status=form.get("status") or "RECEIVED",
            comments=form.get("comments")
        )
        db.session.add(inv)
        db.session.commit()

        # ----- UPDATE PO STATUS TO INVOICED -----
        if inv.po_id:
            po = PurchaseOrder.query.get(inv.po_id)
            if po:
                po.status = "INVOICED"
                db.session.commit()


        if request.is_json:
            return jsonify({
                "id": inv.id,
                "status": inv.status,
                "message": "Invoice created"
            }), 201

        flash("Invoice created successfully.", "success")
        return redirect(url_for("invoices"))

    invoices = Invoice.query.order_by(Invoice.created_at.desc()).all()
    bookings = MediaBooking.query.all()
    pos = PurchaseOrder.query.all()
    return render_template("invoices.html", invoices=invoices, bookings=bookings, pos=pos)


# -------------------------------------------------------
# JSON API ENDPOINTS (for UiPath)
# -------------------------------------------------------

@app.route("/api/media-bookings", methods=["POST"])
def api_create_booking():
    data = request.get_json() or {}

    booking = MediaBooking(
        campaign_name=data.get("campaign_name"),
        channel=data.get("channel"),
        market=data.get("market"),
        vendor=data.get("vendor"),
        start_date=data.get("start_date"),
        end_date=data.get("end_date"),
        unit_rate=float(data.get("unit_rate") or 0),
        units=int(data.get("units") or 0),
        budget=float(data.get("budget") or 0),
        currency=data.get("currency") or "USD",
        status=data.get("status") or "PLANNED"
    )
    db.session.add(booking)
    db.session.commit()
    return jsonify({"id": booking.id, "status": booking.status, "message": "Media booking created"}), 201


@app.route("/api/media-bookings/<int:booking_id>", methods=["GET"])
def api_get_booking(booking_id):
    booking = MediaBooking.query.get_or_404(booking_id)
    return jsonify({
        "id": booking.id,
        "campaign_name": booking.campaign_name,
        "channel": booking.channel,
        "market": booking.market,
        "vendor": booking.vendor,
        "start_date": booking.start_date,
        "end_date": booking.end_date,
        "unit_rate": booking.unit_rate,
        "units": booking.units,
        "budget": booking.budget,
        "currency": booking.currency,
        "status": booking.status
    })


@app.route("/api/purchase-orders", methods=["POST"])
def api_create_po():
    data = request.get_json() or {}

    # booking_id is mandatory for this API
    if not data.get("booking_id"):
        return jsonify({"error": "booking_id is required"}), 400

    # Check if booking exists
    booking = MediaBooking.query.get(data.get("booking_id"))
    if not booking:
        return jsonify({"error": "Invalid booking_id"}), 404

    # PO number logic (API can still auto-generate if not provided)
    po_number = data.get("po_number")
    if po_number:
        existing = PurchaseOrder.query.filter_by(po_number=po_number).first()
        if existing:
            return jsonify({"error": "PO number already exists"}), 409
    else:
        po_number = f"PO-{int(datetime.utcnow().timestamp())}"

    vendor = data.get("vendor") or booking.vendor
    if not vendor:
        return jsonify({"error": "vendor is required"}), 400

    po = PurchaseOrder(
        po_number=po_number,
        vendor=vendor,
        booking_id=int(data.get("booking_id")),
        total_amount=float(data.get("total_amount") or 0),
        currency=data.get("currency") or "USD",
        status=data.get("status") or "CREATED"
    )

    db.session.add(po)
    db.session.commit()

    return jsonify({
        "id": po.id,
        "po_number": po.po_number,
        "booking_id": po.booking_id,
        "status": po.status,
        "message": "PO created successfully"
    }), 201



@app.route("/api/purchase-orders/<int:po_id>", methods=["GET"])
def api_get_po(po_id):
    po = PurchaseOrder.query.get_or_404(po_id)
    return jsonify({
        "id": po.id,
        "po_number": po.po_number,
        "vendor": po.vendor,
        "booking_id": po.booking_id,
        "total_amount": po.total_amount,
        "currency": po.currency,
        "status": po.status
    })


@app.route("/api/invoices", methods=["POST"])
def api_create_invoice():
    data = request.get_json() or {}
    inv = Invoice(
        invoice_number=data.get("invoice_number"),
        vendor=data.get("vendor"),
        booking_id=data.get("booking_id"),
        po_id=data.get("po_id"),
        amount=float(data.get("amount") or 0),
        tax_amount=float(data.get("tax_amount") or 0),
        currency=data.get("currency") or "USD",
        status=data.get("status") or "RECEIVED",
        comments=data.get("comments")
    )
    db.session.add(inv)
    db.session.commit()

    # ----- UPDATE PO STATUS TO INVOICED -----
    if inv.po_id:
        po = PurchaseOrder.query.get(inv.po_id)
        if po:
            po.status = "INVOICED"
            db.session.commit()

    return jsonify({"id": inv.id, "status": inv.status, "message": "Invoice created"}), 201



@app.route("/api/invoices/<int:inv_id>", methods=["GET"])
def api_get_invoice(inv_id):
    inv = Invoice.query.get_or_404(inv_id)
    return jsonify({
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "vendor": inv.vendor,
        "booking_id": inv.booking_id,
        "po_id": inv.po_id,
        "amount": inv.amount,
        "tax_amount": inv.tax_amount,
        "currency": inv.currency,
        "status": inv.status,
        "comments": inv.comments
    })


@app.route("/api/invoices/<int:inv_id>/approve", methods=["POST"])
def api_approve_invoice(inv_id):
    inv = Invoice.query.get_or_404(inv_id)
    inv.status = "APPROVED"
    inv.comments = (inv.comments or "") + "\nAuto-approved by Agent."
    db.session.commit()
    return jsonify({"message": "Invoice approved", "status": inv.status})


@app.route("/api/invoices/<int:inv_id>/flag", methods=["POST"])
def api_flag_invoice(inv_id):
    data = request.get_json() or {}
    inv = Invoice.query.get_or_404(inv_id)
    inv.status = "FLAGGED"
    reason = data.get("reason") or "Flagged for manual review"
    inv.comments = (inv.comments or "") + "\nFLAG: " + reason
    db.session.commit()
    return jsonify({"message": "Invoice flagged", "status": inv.status})


@app.route("/send-invoice/<int:inv_id>", methods=["POST"])
def send_invoice(inv_id):
    inv = Invoice.query.get_or_404(inv_id)

    # Only allow sending once
    if inv.status != "RECEIVED":
        flash("Invoice already processed.", "warning")
        return redirect(url_for("invoices"))

    # Mark invoice as ready for validation
    inv.status = "APPROVED"
    inv.comments = (inv.comments or "") + "\nInvoice sent for validation."
    db.session.commit()

    flash(f"Invoice {inv.invoice_number} sent for validation.", "success")
    return redirect(url_for("invoices"))

@app.route("/api/bookings/<int:booking_id>/has-po", methods=["GET"])
def api_booking_has_po(booking_id):
    booking = MediaBooking.query.get_or_404(booking_id)

    pos = PurchaseOrder.query.filter_by(booking_id=booking_id).all()

    return jsonify({
        "booking_id": booking_id,
        "has_po": len(pos) > 0,
        "po_count": len(pos),
        "purchase_orders": [
            {
                "id": po.id,
                "po_number": po.po_number,
                "status": po.status,
                "amount": po.total_amount,
                "created_at": po.created_at.isoformat()
            }
            for po in pos
        ]
    })
@app.route("/api/media-bookings/all", methods=["GET"])
def api_get_all_bookings():
    bookings = MediaBooking.query.order_by(MediaBooking.created_at.desc()).all()

    return jsonify([
        {
            "id": b.id,
            "campaign_name": b.campaign_name,
            "channel": b.channel,
            "market": b.market,
            "vendor": b.vendor,
            "start_date": b.start_date,
            "end_date": b.end_date,
            "unit_rate": b.unit_rate,
            "units": b.units,
            "budget": b.budget,
            "currency": b.currency,
            "status": b.status,
            "created_at": b.created_at.isoformat()
        }
        for b in bookings
    ])
# -------------------------------------------------------
# MAIN ENTRY (Flask 3 compatible)
# -------------------------------------------------------

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
