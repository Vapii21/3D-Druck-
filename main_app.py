import sys
import sqlite3
import re
from pathlib import Path
import pandas as pd

from PySide6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout,
                               QWidget, QLabel, QStackedWidget, QFormLayout,
                               QLineEdit, QDialog, QDialogButtonBox, QTableWidget,
                               QTableWidgetItem, QMessageBox, QFileDialog, QMenu)
from PySide6.QtCore import Qt

from produkt_upload import ProduktUploadWidget

# TODO: Pfad für Produktivbetrieb dynamisch oder über config.ini / .env anpassen
EXCEL_PFAD = "D:/3D-Druck/CODE/Druckkosten_Uebersicht.xlsx"

def init_db():
    """Initialisiert die lokale SQLite-Datenbank für die Datenhaltung."""
    conn = sqlite3.connect("druckkosten.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS druckkosten (
                    id INTEGER PRIMARY KEY,
                    daten_json TEXT
                )''')
    conn.commit()
    conn.close()

def analysiere_datei(pfad):
    """Entscheidet basierend auf der Dateiendung, welcher Parser genutzt wird."""
    if pfad.lower().endswith(".gcode"):
        return analysiere_gcode(pfad)
    elif pfad.lower().endswith(".3mf"):
        return analysiere_3mf(pfad)
    return {}

def analysiere_gcode(pfad):
    """Analysiert eine GCode-Datei und extrahiert Druckdauer sowie Materialgewicht."""
    result = {'Dateiname': Path(pfad).name}
    try:
        with open(pfad, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                if "total estimated time:" in line.lower():
                    match = re.search(r'total estimated time:\s*(\d+)h (\d+)m (\d+)s', line, re.IGNORECASE)
                    if match:
                        result['Druckdauer'] = f"{match.group(1)}h {match.group(2)}m {match.group(3)}s"
                elif "total filament weight [g]" in line.lower():
                    match = re.search(r'([\d.]+)', line)
                    if match:
                        result['material_gramm'] = round(float(match.group(1)), 2)
    except Exception as e:
         print(f"Fehler beim Analysieren der GCode-Datei {pfad}: {e}")
         return {}
    return result

def analysiere_3mf(pfad):
    """Extrahiert die GCode-Daten aus einer komprimierten 3MF-Zieldatei."""
    import zipfile
    result = {'Dateiname': Path(pfad).name}
    try:
        with zipfile.ZipFile(pfad, 'r') as zipf:
            for file in zipf.namelist():
                if file.lower().endswith(".gcode"):
                    with zipf.open(file) as gcode_file:
                        lines = [line.decode('utf-8', errors='ignore') for line in gcode_file.readlines()]
                        for line in lines:
                            if "total estimated time:" in line.lower():
                                match = re.search(r'total estimated time:\s*(\d+)h (\d+)m (\d+)s', line, re.IGNORECASE)
                                if match:
                                    result['Druckdauer'] = f"{match.group(1)}h {match.group(2)}m {match.group(3)}s"
                            elif "total filament weight [g]" in line.lower():
                                match = re.search(r'([\d.]+)', line)
                                if match:
                                    result['material_gramm'] = round(float(match.group(1)), 2)
                    break
    except Exception as e:
        QMessageBox.warning(None, "Analyse-Fehler", f"Fehler bei 3MF-Extraktion: {str(e)}")
        return {}
    return result

def exportiere_nach_excel(df):
    """Speichert den aktuellen Berechnungsstand in der Excel-Tabelle."""
    try:
        df.to_excel(EXCEL_PFAD, index=False)
    except Exception as e:
        QMessageBox.warning(None, "Fehler beim Speichern", f"Excel-Export fehlgeschlagen: {str(e)}")

def lade_excel():
    """Lädt die bestehende Excel-Übersicht oder erzeugt eine leere Struktur mit Pflichtspalten."""
    expected_columns = [
        'Dateiname', 'Druckdauer', 'material_gramm',
        'Fixe Stromkosten (€/kWh)', 'Grundpreis mtl. (€)', 'Material kosten pro kg (€/kg)',
        'Verbrauch Durchschnittlich (W)', 'Grundpreis Stunde (€/h)', 'Stromverbrauch (kWh)',
        'Stromkosten (€)', 'Grundpreis Strom (€)', 'Stromkosten ges (€)',
        'Kosten Material (€)', 'Kosten gesamt (€)'
    ]
    try:
        df = pd.read_excel(EXCEL_PFAD)
        for col in expected_columns:
            if col not in df.columns:
                df[col] = None
        return df.reindex(columns=expected_columns)
    except FileNotFoundError:
        return pd.DataFrame(columns=expected_columns)
    except Exception as e:
        QMessageBox.warning(None, "Fehler beim Laden", f"Fehler beim Laden der Excel-Datei: {str(e)}")
        return pd.DataFrame(columns=expected_columns)

def druckdauer_zu_stunden(druckdauer_str):
    """Konvertiert Format '1h 30m 0s' in einen mathematisch verwertbaren Float-Stundenwert."""
    if not isinstance(druckdauer_str, str):
        return 0.0
    match = re.match(r'(\d+)h (\d+)m (\d+)s', druckdauer_str)
    if match:
        return int(match.group(1)) + int(match.group(2))/60 + int(match.group(3))/3600
    return 0.0

def fuehre_berechnungen_durch(row):
    """Kalkuliert alle spezifischen Strom- und Materialkosten für einen Druckjob."""
    try:
        druckdauer_str = row.get('Druckdauer', '0h 0m 0s')
        material_gramm = pd.to_numeric(row.get('material_gramm', 0), errors='coerce') or 0
        fixe_stromkosten_kwh = pd.to_numeric(row.get('Fixe Stromkosten (€/kWh)', 0), errors='coerce') or 0
        grundpreis_mtl = pd.to_numeric(row.get('Grundpreis mtl. (€)', 0), errors='coerce') or 0
        material_kosten_kg = pd.to_numeric(row.get('Material kosten pro kg (€/kg)', 0), errors='coerce') or 0
        verbrauch_durchschnittlich_w = pd.to_numeric(row.get('Verbrauch Durchschnittlich (W)', 0), errors='coerce') or 0

        druckdauer_stunden = druckdauer_zu_stunden(druckdauer_str)

        # Kosten-Algorithmen
        grundpreis_stunde = (grundpreis_mtl * 12) / 365 / 24 if grundpreis_mtl > 0 else 0
        stromverbrauch_kwh = (druckdauer_stunden * verbrauch_durchschnittlich_w) / 1000 if verbrauch_durchschnittlich_w > 0 else 0
        stromkosten = stromverbrauch_kwh * fixe_stromkosten_kwh
        grundpreis_strom = druckdauer_stunden * grundpreis_stunde
        stromkosten_ges = stromkosten + grundpreis_strom
        kosten_material = (material_gramm / 1000) * material_kosten_kg
        kosten_gesamt = stromkosten_ges + kosten_material

        row['Grundpreis Stunde (€/h)'] = round(grundpreis_stunde, 4)
        row['Stromverbrauch (kWh)'] = round(stromverbrauch_kwh, 4)
        row['Stromkosten (€)'] = round(stromkosten, 4)
        row['Grundpreis Strom (€)'] = round(grundpreis_strom, 4)
        row['Stromkosten ges (€)'] = round(stromkosten_ges, 4)
        row['Kosten Material (€)'] = round(kosten_material, 4)
        row['Kosten gesamt (€)'] = round(kosten_gesamt, 4)

    except Exception as e:
        print(f"Fehler bei Berechnung für Zeile: {row.get('Dateiname', 'Unbekannt')} - {e}")
        for key in ['Grundpreis Stunde (€/h)', 'Stromverbrauch (kWh)', 'Stromkosten (€)',
                    'Grundpreis Strom (€)', 'Stromkosten ges (€)', 'Kosten Material (€)', 'Kosten gesamt (€)']:
            row[key] = None

    return row

class ManuelleEingabeDialog(QDialog):
    """Modal-Dialog zur Abfrage variabler Kostenfaktoren nach dem Datei-Import."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Kostenparameter eingeben")
        self.setModal(True)

        layout = QFormLayout()

        self.le_stromkosten_kwh = QLineEdit()
        self.le_stromkosten_kwh.setPlaceholderText("z.B. 0.30")
        layout.addRow("Fixe Stromkosten (€/kWh):", self.le_stromkosten_kwh)

        self.le_grundpreis_mtl = QLineEdit()
        self.le_grundpreis_mtl.setPlaceholderText("z.B. 10.00")
        layout.addRow("Grundpreis mtl. (€):", self.le_grundpreis_mtl)

        self.le_material_kosten_kg = QLineEdit()
        self.le_material_kosten_kg.setPlaceholderText("z.B. 20.00")
        layout.addRow("Materialkosten pro kg (€/kg):", self.le_material_kosten_kg)

        self.le_verbrauch_watt = QLineEdit()
        self.le_verbrauch_watt.setPlaceholderText("z.B. 125")
        layout.addRow("Durchschnittlicher Verbrauch (W):", self.le_verbrauch_watt)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.setLayout(layout)

    def get_values(self):
        try:
            fixe_stromkosten = float(self.le_stromkosten_kwh.text().replace(',', '.')) if self.le_stromkosten_kwh.text() else 0.0
            grundpreis_mtl = float(self.le_grundpreis_mtl.text().replace(',', '.')) if self.le_grundpreis_mtl.text() else 0.0
            material_kosten_kg = float(self.le_material_kosten_kg.text().replace(',', '.')) if self.le_material_kosten_kg.text() else 0.0
            verbrauch_watt = float(self.le_verbrauch_watt.text().replace(',', '.')) if self.le_verbrauch_watt.text() else 0.0
            return fixe_stromkosten, grundpreis_mtl, material_kosten_kg, verbrauch_watt
        except ValueError:
            QMessageBox.warning(self, "Ungültige Eingabe", "Bitte numerische Werte eingeben.")
            return None

class StartScreenWidget(QWidget):
    """Zentrales Dashboard zur Navigation zwischen Kalkulation und Marktplatz-Uploads."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        self.label = QLabel("3D-Druck ERP & Multi-Channel Upload Tool")
        self.label.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 20px;")
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

        self.btn_druckkosten = QPushButton("3D-Druck Kosten berechnen")
        self.btn_druckkosten.setMinimumHeight(40)
        layout.addWidget(self.btn_druckkosten)

        self.btn_produkt_upload = QPushButton("Produkte verwalten (Etsy & eBay)")
        self.btn_produkt_upload.setMinimumHeight(40)
        layout.addWidget(self.btn_produkt_upload)

        layout.addStretch()

class HauptFenster(QMainWindow):
    """Zentrale Anwendungskomponente mit QStackedWidget-Navigation."""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D-Druck Core Tool Suite")
        self.setGeometry(100, 100, 1100, 750)

        self.start_screen = StartScreenWidget(self)
        self.druckkosten_widget = QWidget()
        self.produkt_upload_widget = ProduktUploadWidget(self)

        self.setup_druckkosten_ui()

        self.stack = QStackedWidget()
        self.stack.addWidget(self.start_screen)       # Index 0
        self.stack.addWidget(self.druckkosten_widget)  # Index 1
        self.stack.addWidget(self.produkt_upload_widget) # Index 2

        self.setCentralWidget(self.stack)

        # Event-Verknüpfungen Dashboard
        self.start_screen.btn_druckkosten.clicked.connect(self.zeige_druckkosten_ansicht)
        self.start_screen.btn_produkt_upload.clicked.connect(self.zeige_produkt_upload_ansicht)
        self.produkt_upload_widget.btn_back_to_start.clicked.connect(self.zeige_start_ansicht)

        self.datenframe = lade_excel()

    def setup_druckkosten_ui(self):
        """Erstellt die Oberfläche für die tabellarische Kostenübersicht."""
        layout = QVBoxLayout(self.druckkosten_widget)
        layout.addWidget(QLabel("Kostenanalyse & GCode Import"))

        self.btn_export = QPushButton("Tabelle anzeigen und bearbeiten")
        self.btn_export.clicked.connect(self.zeige_druckkosten_tabelle)
        layout.addWidget(self.btn_export)

        self.btn_gcode_laden = QPushButton("GCode / 3MF-Datei einlesen")
        self.btn_gcode_laden.clicked.connect(self.lade_gcode_datei)
        layout.addWidget(self.btn_gcode_laden)

        self.btn_excel_speichern = QPushButton("Änderungen in Excel sichern")
        self.btn_excel_speichern.clicked.connect(self.speichere_excel_datei)
        layout.addWidget(self.btn_excel_speichern)

        self.export_table = QTableWidget()
        layout.addWidget(self.export_table)
        self.export_table.hide()

        # Tabellenkonfiguration & Drag&Drop Vorbereitung
        self.export_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.export_table.customContextMenuRequested.connect(self.zeige_kontextmenue)
        self.export_table.cellChanged.connect(self.handle_cell_changed)

        self.export_table.setDragEnabled(True)
        self.export_table.setAcceptDrops(True)
        self.export_table.setDragDropMode(QTableWidget.InternalMove)
        self.export_table.setDropIndicatorShown(True)

        self.back_button_druckkosten = QPushButton("Zurück zum Hauptmenü")
        self.back_button_druckkosten.clicked.connect(self.zeige_start_ansicht)
        layout.addWidget(self.back_button_druckkosten)

    def zeige_start_ansicht(self):
        self.stack.setCurrentIndex(0)

    def zeige_druckkosten_ansicht(self):
        self.stack.setCurrentIndex(1)
        self.datenframe = lade_excel()

    def zeige_druckkosten_tabelle(self):
        self.export_table.show()
        self.aktualisiere_export_tabelle()

    def zeige_produkt_upload_ansicht(self):
        self.stack.setCurrentIndex(2)

    def aktualisiere_export_tabelle(self):
        """Rendert den Pandas DataFrame synchron in das QTableWidget."""
        df = self.datenframe
        self.export_table.blockSignals(True)
        self.export_table.setRowCount(len(df))
        self.export_table.setColumnCount(len(df.columns))
        self.export_table.setHorizontalHeaderLabels(df.columns.astype(str).tolist())

        editable_cols = ['Fixe Stromkosten (€/kWh)', 'Grundpreis mtl. (€)', 'Material kosten pro kg (€/kg)', 'Verbrauch Durchschnittlich (W)']

        for i in range(len(df)):
            for j in range(len(df.columns)):
                item = QTableWidgetItem(str(df.iat[i, j]))
                header = df.columns[j]
                if header in editable_cols:
                     item.setFlags(Qt.ItemIsEditable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                else:
                     item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

                self.export_table.setItem(i, j, item)

        self.export_table.blockSignals(False)

    def zeige_kontextmenue(self, position):
        menu = QMenu()
        delete_action = menu.addAction("Zeile löschen")
        action = menu.exec(self.export_table.viewport().mapToGlobal(position))
        if action == delete_action:
            self.loesche_ausgewaehlte_zeilen()

    def loesche_ausgewaehlte_zeilen(self):
        selected_rows = sorted(list(set(index.row() for index in self.export_table.selectedIndexes())))
        if not selected_rows:
            return

        reply = QMessageBox.question(self, 'Datensatz löschen',
                                     f"Möchten Sie die gewählten {len(selected_rows)} Zeile(n) unwiderruflich entfernen?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            rows_to_delete = sorted(selected_rows, reverse=True)
            for row_index in rows_to_delete:
                self.datenframe = self.datenframe.drop(self.datenframe.index[row_index]).reset_index(drop=True)

            self.aktualisiere_export_tabelle()

    def handle_cell_changed(self, row, column):
        """Verarbeitet Inline-Edits der Preiskomponenten und triggert die Neukalkulation."""
        item = self.export_table.item(row, column)
        if item is not None:
            new_value_str = item.text()
            col_name = self.datenframe.columns[column]
            manual_cols = ['Fixe Stromkosten (€/kWh)', 'Grundpreis mtl. (€)', 'Material kosten pro kg (€/kg)', 'Verbrauch Durchschnittlich (W)']

            try:
                if col_name in manual_cols:
                     new_value = float(new_value_str.replace(',', '.')) if new_value_str else 0.0
                else:
                    new_value = new_value_str

                self.datenframe.at[row, col_name] = new_value

                if col_name in manual_cols:
                    updated_row_data = self.datenframe.iloc[row].to_dict()
                    calculated_row_data = fuehre_berechnungen_durch(updated_row_data)
                    for key, value in calculated_row_data.items():
                         self.datenframe.at[row, key] = value

                    self.aktualisiere_export_tabelle()

            except ValueError:
                QMessageBox.warning(self, "Typkonflikt", f"Ungültiger numerischer Wert für Spalte '{col_name}'.")
                self.export_table.blockSignals(True)
                self.export_table.setItem(row, column, QTableWidgetItem(str(self.datenframe.iat[row, column])))
                self.export_table.blockSignals(False)
            except Exception as e:
                print(f"Fehler bei Zelländerung: {e}")

    def lade_gcode_datei(self):
        """Führt den Datei-Import-Workflow inklusive Parametrisierung aus."""
        options = QFileDialog.Options()
        pfad, _ = QFileDialog.getOpenFileName(self, "3D-Druck-Datei importieren", "", "Slicer-Dateien (*.gcode *.3mf);;Alle Dateien (*)", options=options)
        if pfad:
            daten = analysiere_datei(pfad)
            if daten:
                eingabe_dialog = ManuelleEingabeDialog(self)
                if eingabe_dialog.exec() == QDialog.Accepted:
                    manuelle_werte = eingabe_dialog.get_values()
                    if manuelle_werte:
                        fixe_stromkosten, grundpreis_mtl, material_kosten_kg, verbrauch_watt = manuelle_werte

                        neue_zeile_data = {
                            'Dateiname': daten.get('Dateiname', Path(pfad).name),
                            'Druckdauer': daten.get('Druckdauer', '0h 0m 0s'),
                            'material_gramm': daten.get('material_gramm', 0),
                            'Fixe Stromkosten (€/kWh)': fixe_stromkosten,
                            'Grundpreis mtl. (€)': grundpreis_mtl,
                            'Material kosten pro kg (€/kg)': material_kosten_kg,
                            'Verbrauch Durchschnittlich (W)': verbrauch_watt,
                            'Grundpreis Stunde (€/h)': None, 'Stromverbrauch (kWh)': None,
                            'Stromkosten (€)': None, 'Grundpreis Strom (€)': None,
                            'Stromkosten ges (€)': None, 'Kosten Material (€)': None, 'Kosten gesamt (€)': None
                        }

                        neue_zeile_df = pd.DataFrame([neue_zeile_data]).apply(fuehre_berechnungen_durch, axis=1)
                        self.datenframe = pd.concat([self.datenframe, neue_zeile_df], ignore_index=True)

                        if self.export_table.isVisible():
                            self.aktualisiere_export_tabelle()
                        QMessageBox.information(self, "Erfolg", "Druckjob erfolgreich einkalkuliert.")

    def speichere_excel_datei(self):
        exportiere_nach_excel(self.datenframe)
        QMessageBox.information(self, "Gespeichert", "Daten erfolgreich in Excel-Tabelle synchronisiert.")

if __name__ == "__main__":
    init_db()
    app = QApplication(sys.argv)
    fenster = HauptFenster()
    fenster.show()
    sys.exit(app.exec())