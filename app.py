import io
import os
import pandas as pd
from flask import Flask, render_template, request, send_file, flash, redirect, url_for

app = Flask(__name__)
app.secret_key = "concabom-secret"

ALLOWED_EXTENSIONS = {"csv"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def merge_boms(files, sep=","):
    """Merge multiple BOM DataFrames: sum Quantity for matching References."""
    dfs = []
    for f in files:
        content = f.read().decode("utf-8-sig")
        df = pd.read_csv(io.StringIO(content), sep=sep)
        df.columns = df.columns.str.strip()
        # Strip whitespace (spaces, tabs) from all string columns
        df = df.apply(lambda col: col.str.strip() if pd.api.types.is_string_dtype(col) else col)
        dfs.append(df)

    combined = pd.concat(dfs, ignore_index=True)

    # Detect column names case-insensitively
    col_map = {c.lower(): c for c in combined.columns}
    ref_col = col_map.get("reference") or col_map.get("ref") or col_map.get("pn")
    qty_col = col_map.get("quantity") or col_map.get("qty") or col_map.get("quantite") or col_map.get("quantité")
    desc_col = col_map.get("description") or col_map.get("descritption") or col_map.get("designation")

    if not ref_col or not qty_col:
        raise ValueError(f"Colonnes requises introuvables. Colonnes détectées : {list(combined.columns)}")

    combined[qty_col] = pd.to_numeric(combined[qty_col], errors="coerce").fillna(0)

    agg = {qty_col: "sum"}
    if desc_col:
        agg[desc_col] = "first"

    result = combined.groupby(ref_col, as_index=False).agg(agg)

    # Reorder columns: description, reference, quantity
    ordered = []
    if desc_col and desc_col in result.columns:
        ordered.append(desc_col)
    ordered.append(ref_col)
    ordered.append(qty_col)
    result = result[ordered]

    return result


@app.route("/", methods=["GET", "POST"])
def index():
    result_table = None
    csv_data = None

    if request.method == "POST":
        files = request.files.getlist("bom_files")
        valid_files = [f for f in files if f and f.filename and allowed_file(f.filename)]

        if len(valid_files) < 2:
            flash("Veuillez uploader au moins 2 fichiers CSV.", "error")
            return redirect(url_for("index"))

        sep = request.form.get("separator", ",")
        if sep not in (",", ";"):
            sep = ","
        try:
            result = merge_boms(valid_files, sep=sep)
            result_table = result.to_html(index=False, classes="result-table", border=0)
            csv_data = result.to_csv(index=False, sep=sep)
        except ValueError as e:
            flash(str(e), "error")
        except Exception as e:
            flash(f"Erreur lors de la fusion : {e}", "error")

    return render_template("index.html", result_table=result_table, csv_data=csv_data)


@app.route("/download", methods=["POST"])
def download():
    csv_data = request.form.get("csv_data", "")
    buf = io.BytesIO(csv_data.encode("utf-8"))
    buf.seek(0)
    return send_file(buf, mimetype="text/csv", as_attachment=True, download_name="BOM_result.csv")


if __name__ == "__main__":
    app.run(debug=True)
