"""
Interface graphique pour le couple-mètre DYN-200
Communication MODBUS RTU via RS485 (convertisseur RS232-RS485)

Dépendances : pip install pymodbus pyserial matplotlib
"""

import tkinter as tk
from tkinter import ttk, messagebox, font
import threading
import time
import struct
import serial
import serial.tools.list_ports
from collections import deque
import sys

# --- Matplotlib pour les graphiques ---
try:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.animation import FuncAnimation
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

# --- PyModbus ---
try:
    from pymodbus.client import ModbusSerialClient
    from pymodbus.exceptions import ModbusException
    HAS_MODBUS = True
except ImportError:
    HAS_MODBUS = False

# ─────────────────────────────────────────────────────────────────────────────
#  REGISTRES DYN-200 (adresses MODBUS, mode lecture 03H)
#  Toutes les valeurs sont des int 32 bits (2 registres de 16 bits chacun)
# ─────────────────────────────────────────────────────────────────────────────
REGS = {
    "Couple (N·m)":          0x00,   # Torque
    "Vitesse (RPM)":         0x02,   # Speed
    "Puissance (×0.1 kW)":   0x04,   # Power
    "Filtrage numérique":    0x06,   # Digital filtering
    "Point décimal":         0x08,   # Decimal point
    "Zéro au démarrage":     0x0A,   # Boot zero
    "Zéro transmission":     0x0C,   # Send zero
    "Pleine échelle":        0x0E,   # Change to full degree
    "Plage transmission":    0x10,   # Transform quantity range
    "Direction couple":      0x12,   # Torque direction
    "Filtre vitesse":        0x1E,   # Speed filter
    "Décimales vitesse":     0x20,   # Speed decimal
}

# Registres de mesure principaux (affichés en grand)
LIVE_REGS = {
    "couple":    (0x00, "N·m",  "#00D4FF"),
    "vitesse":   (0x02, "RPM",  "#00FF9F"),
    "puissance": (0x04, "W",   "#FFB300"),
}

HISTORY_LEN = 200   # points conservés dans les graphiques

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers MODBUS
# ─────────────────────────────────────────────────────────────────────────────

def regs_to_int32(regs):
    """Convertit deux registres 16 bits en entier signé 32 bits."""
    raw = (regs[0] << 16) | regs[1]
    return struct.unpack(">i", struct.pack(">I", raw))[0]


# ─────────────────────────────────────────────────────────────────────────────
#  Application principale
# ─────────────────────────────────────────────────────────────────────────────

class DYN200App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("DYN-200 — Interface MODBUS RTU")
        self.configure(bg="#1A1A2E")
        self.resizable(True, True)
        self.minsize(900, 620)

        # État
        self.client = None
        self.connected = False
        self.polling = False
        self.poll_thread = None
        self.slave_id = tk.IntVar(value=1)
        self.baud_var = tk.StringVar(value="19200")
        self.port_var = tk.StringVar()
        self.poll_interval = tk.DoubleVar(value=0.2)   # secondes

        # Historiques
        self.history = {k: deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)
                        for k in ["couple", "vitesse", "puissance"]}
        self.timestamps = deque([i * 0.2 for i in range(HISTORY_LEN)],
                                maxlen=HISTORY_LEN)
        self.t_elapsed = HISTORY_LEN * 0.2

        # Variables d'affichage
        self.live_vars = {k: tk.StringVar(value="—") for k in LIVE_REGS}
        self.reg_vars  = {k: tk.StringVar(value="—") for k in REGS}
        self.status_var = tk.StringVar(value="⬤  Déconnecté")
        self.log_lines = []

        self._build_ui()
        self._refresh_ports()

        if HAS_MATPLOTLIB:
            self._start_animation()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Construction UI ────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Barre du haut (connexion) ──
        top = tk.Frame(self, bg="#16213E", pady=6)
        top.pack(fill="x")
        self._build_toolbar(top)

        # ── Corps principal ──
        body = tk.PanedWindow(self, orient="horizontal", bg="#1A1A2E",
                              sashwidth=6, sashrelief="flat")
        body.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Colonne gauche : mesures live + paramètres
        left = tk.Frame(body, bg="#1A1A2E")
        body.add(left, minsize=320)

        self._build_live_panel(left)
        self._build_params_panel(left)
        self._build_controls_panel(left)
        self._build_log_panel(left)

        # Colonne droite : graphiques
        right = tk.Frame(body, bg="#1A1A2E")
        body.add(right, minsize=400)

        if HAS_MATPLOTLIB:
            self._build_graph_panel(right)
        else:
            tk.Label(right, text="📦 Installer matplotlib\npour les graphiques",
                     bg="#1A1A2E", fg="#888", font=("Helvetica", 13),
                     justify="center").pack(expand=True)

    # ── Toolbar ───────────────────────────────────────────────────────────

    def _build_toolbar(self, parent):
        tk.Label(parent, text="DYN-200", bg="#16213E", fg="#00D4FF",
                 font=("Helvetica", 16, "bold")).pack(side="left", padx=12)

        # Port
        tk.Label(parent, text="Port:", bg="#16213E", fg="#CCC",
                 font=("Helvetica", 10)).pack(side="left", padx=(8, 2))
        self.port_cb = ttk.Combobox(parent, textvariable=self.port_var,
                                    width=10, state="readonly")
        self.port_cb.pack(side="left")
        tk.Button(parent, text="⟳", bg="#16213E", fg="#00D4FF",
                  relief="flat", font=("Helvetica", 12),
                  command=self._refresh_ports).pack(side="left", padx=2)

        # Baud
        tk.Label(parent, text="Baud:", bg="#16213E", fg="#CCC",
                 font=("Helvetica", 10)).pack(side="left", padx=(8, 2))
        baud_cb = ttk.Combobox(parent, textvariable=self.baud_var,
                               values=["9600","14400","19200","38400",
                                       "57600","115200"],
                               width=8, state="readonly")
        baud_cb.pack(side="left")

        # Adresse esclave
        tk.Label(parent, text="Esclave:", bg="#16213E", fg="#CCC",
                 font=("Helvetica", 10)).pack(side="left", padx=(8, 2))
        tk.Spinbox(parent, from_=1, to=120, textvariable=self.slave_id,
                   width=4, bg="#0F3460", fg="white",
                   buttonbackground="#0F3460",
                   relief="flat").pack(side="left")

        # Intervalle
        tk.Label(parent, text="Période (s):", bg="#16213E", fg="#CCC",
                 font=("Helvetica", 10)).pack(side="left", padx=(8, 2))
        tk.Spinbox(parent, from_=0.05, to=5.0, increment=0.05,
                   textvariable=self.poll_interval,
                   width=5, format="%.2f",
                   bg="#0F3460", fg="white",
                   buttonbackground="#0F3460",
                   relief="flat").pack(side="left")

        # Bouton connexion
        self.btn_connect = tk.Button(
            parent, text="  Connecter  ",
            bg="#00D4FF", fg="#000", font=("Helvetica", 10, "bold"),
            relief="flat", padx=6,
            command=self._toggle_connection)
        self.btn_connect.pack(side="left", padx=12)

        # Statut
        self.lbl_status = tk.Label(parent, textvariable=self.status_var,
                                   bg="#16213E", fg="#FF4444",
                                   font=("Helvetica", 10, "bold"))
        self.lbl_status.pack(side="right", padx=12)

    # ── Live panel (couple / vitesse / puissance) ─────────────────────────

    def _build_live_panel(self, parent):
        frame = tk.LabelFrame(parent, text=" Mesures en temps réel ",
                              bg="#16213E", fg="#00D4FF",
                              font=("Helvetica", 10, "bold"),
                              relief="flat", bd=2)
        frame.pack(fill="x", padx=6, pady=(6, 4))

        for key, (_, unit, color) in LIVE_REGS.items():
            row = tk.Frame(frame, bg="#16213E")
            row.pack(fill="x", padx=8, pady=4)

            label_text = {"couple": "Couple", "vitesse": "Vitesse",
                          "puissance": "Puissance"}[key]
            tk.Label(row, text=label_text, width=10, anchor="w",
                     bg="#16213E", fg="#AAA",
                     font=("Helvetica", 10)).pack(side="left")

            tk.Label(row, textvariable=self.live_vars[key],
                     width=12, anchor="e",
                     bg="#0F3460", fg=color,
                     font=("Courier", 18, "bold"),
                     relief="flat", padx=4).pack(side="left", padx=4)

            tk.Label(row, text=unit, bg="#16213E", fg=color,
                     font=("Helvetica", 10, "bold")).pack(side="left")

    # ── Panneau paramètres ────────────────────────────────────────────────

    def _build_params_panel(self, parent):
        outer = tk.LabelFrame(parent, text=" Paramètres MODBUS (lecture) ",
                              bg="#16213E", fg="#00D4FF",
                              font=("Helvetica", 10, "bold"),
                              relief="flat", bd=2)
        outer.pack(fill="x", padx=6, pady=4)

        canvas = tk.Canvas(outer, bg="#16213E", height=190,
                           highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg="#16213E")
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(
                       scrollregion=canvas.bbox("all")))

        for i, (name, _) in enumerate(REGS.items()):
            bg = "#1A2744" if i % 2 == 0 else "#16213E"
            row = tk.Frame(inner, bg=bg)
            row.pack(fill="x")
            tk.Label(row, text=name, width=24, anchor="w",
                     bg=bg, fg="#CCC",
                     font=("Helvetica", 9)).pack(side="left", padx=4)
            tk.Entry(row, textvariable=self.reg_vars[name],
                     width=14, state="readonly",
                     readonlybackground="#0F3460",
                     fg="#FFD700",
                     relief="flat",
                     font=("Courier", 9)).pack(side="left", padx=4, pady=1)

    # ── Panneau boutons de commande ───────────────────────────────────────

    def _build_controls_panel(self, parent):
        frame = tk.LabelFrame(parent, text=" Commandes ",
                              bg="#16213E", fg="#00D4FF",
                              font=("Helvetica", 10, "bold"),
                              relief="flat", bd=2)
        frame.pack(fill="x", padx=6, pady=4)

        btn_cfg = [
            ("🔄  Lire tout",        self._read_all,        "#00D4FF", "#000"),
            ("⭕  Remise à zéro",     self._send_zero,       "#FF8800", "#000"),
            ("🏭  Reset usine",       self._factory_reset,   "#FF4444", "#FFF"),
            ("📋  Exporter log",      self._export_log,      "#9B59B6", "#FFF"),
        ]
        for i, (txt, cmd, bg, fg) in enumerate(btn_cfg):
            tk.Button(frame, text=txt, command=cmd,
                      bg=bg, fg=fg, font=("Helvetica", 9, "bold"),
                      relief="flat", padx=6, pady=3,
                      activebackground="#1A1A2E",
                      activeforeground=bg).grid(
                row=i // 2, column=i % 2,
                padx=6, pady=4, sticky="ew")
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

    # ── Journal ───────────────────────────────────────────────────────────

    def _build_log_panel(self, parent):
        frame = tk.LabelFrame(parent, text=" Journal ",
                              bg="#16213E", fg="#00D4FF",
                              font=("Helvetica", 10, "bold"),
                              relief="flat", bd=2)
        frame.pack(fill="both", expand=True, padx=6, pady=(4, 6))

        self.log_box = tk.Text(frame, height=6, bg="#0A0A1A", fg="#AAA",
                               font=("Courier", 8), state="disabled",
                               relief="flat", wrap="word")
        sb2 = ttk.Scrollbar(frame, command=self.log_box.yview)
        self.log_box.configure(yscrollcommand=sb2.set)
        sb2.pack(side="right", fill="y")
        self.log_box.pack(fill="both", expand=True)

    # ── Graphiques matplotlib ─────────────────────────────────────────────

    def _build_graph_panel(self, parent):
        frame = tk.LabelFrame(parent, text=" Graphiques temps réel ",
                              bg="#16213E", fg="#00D4FF",
                              font=("Helvetica", 10, "bold"),
                              relief="flat", bd=2)
        frame.pack(fill="both", expand=True, padx=6, pady=6)

        self.fig = Figure(figsize=(6, 7), facecolor="#16213E")
        self.fig.subplots_adjust(hspace=0.45, left=0.12, right=0.97,
                                 top=0.93, bottom=0.08)

        colors  = ["#00D4FF", "#00FF9F", "#FFB300"]
        ylabels = ["N·m", "RPM", "W"]
        titles  = ["Couple", "Vitesse", "Puissance"]

        self.axes = []
        self.lines = []
        for i, (col, yl, tit) in enumerate(zip(colors, ylabels, titles)):
            ax = self.fig.add_subplot(3, 1, i + 1)
            ax.set_facecolor("#0F3460")
            ax.tick_params(colors="#AAA", labelsize=7)
            for spine in ax.spines.values():
                spine.set_edgecolor("#333")
            ax.set_ylabel(yl, color=col, fontsize=8)
            ax.set_title(tit, color=col, fontsize=9, pad=3)
            ax.yaxis.label.set_color(col)
            line, = ax.plot([], [], color=col, linewidth=1.5)
            self.axes.append(ax)
            self.lines.append(line)

        self.canvas_fig = FigureCanvasTkAgg(self.fig, master=frame)
        self.canvas_fig.draw()
        self.canvas_fig.get_tk_widget().pack(fill="both", expand=True)

    def _start_animation(self):
        self.anim = FuncAnimation(
            self.fig, self._update_graph,
            interval=300, blit=False, cache_frame_data=False)

    def _update_graph(self, frame):
        keys = ["couple", "vitesse", "puissance"]
        for i, key in enumerate(keys):
            data = list(self.history[key])
            t    = list(self.timestamps)
            self.lines[i].set_data(t, data)
            self.axes[i].set_xlim(t[0], t[-1])
            ymin, ymax = min(data), max(data)
            margin = max(abs(ymax - ymin) * 0.1, 0.5)
            self.axes[i].set_ylim(ymin - margin, ymax + margin)
        return self.lines

    # ── Connexion / Déconnexion ───────────────────────────────────────────

    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cb["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def _toggle_connection(self):
        if self.connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        if not HAS_MODBUS:
            messagebox.showerror("Erreur",
                "pymodbus non installé.\n"
                "Lancez : pip install pymodbus pyserial")
            return

        port = self.port_var.get()
        if not port:
            messagebox.showwarning("Avertissement", "Sélectionnez un port COM.")
            return

        try:
            self.client = ModbusSerialClient(
                port=port,
                baudrate=int(self.baud_var.get()),
                bytesize=8,
                parity="N",
                stopbits=2,
                timeout=1,
            )
            if not self.client.connect():
                raise ConnectionError("Impossible d'ouvrir le port.")

            self.connected = True
            self.btn_connect.configure(text="  Déconnecter  ",
                                       bg="#FF4444", fg="#FFF")
            self.status_var.set("⬤  Connecté")
            self.lbl_status.configure(fg="#00FF9F")
            self._log(f"✅ Connecté sur {port} @ {self.baud_var.get()} baud")

            # Démarrer le polling
            self.polling = True
            self.poll_thread = threading.Thread(
                target=self._poll_loop, daemon=True)
            self.poll_thread.start()

        except Exception as e:
            self._log(f"❌ Erreur connexion : {e}")
            messagebox.showerror("Erreur de connexion", str(e))

    def _disconnect(self):
        self.polling = False
        if self.poll_thread:
            self.poll_thread.join(timeout=2)
        if self.client:
            self.client.close()
            self.client = None
        self.connected = False
        self.btn_connect.configure(text="  Connecter  ",
                                   bg="#00D4FF", fg="#000")
        self.status_var.set("⬤  Déconnecté")
        self.lbl_status.configure(fg="#FF4444")
        self._log("🔌 Déconnecté.")

    # ── Boucle de polling ─────────────────────────────────────────────────

    def _poll_loop(self):
        while self.polling and self.client:
            try:
                self._read_live()
                self._read_all_params()
            except Exception as e:
                self._log(f"⚠️  Erreur polling : {e}")
            time.sleep(self.poll_interval.get())

    def _read_live(self):
        """Lit couple, vitesse, puissance et met à jour l'UI + historique."""
        uid = self.slave_id.get()
        # Lire 6 registres à partir de 0x00 (couple + vitesse + puissance)
        result = self.client.read_holding_registers(
            address=0x00, count=6, device_id=uid)
        if result.isError():
            self._log(f"⚠️  Lecture live échouée : {result}")
            return

        regs = result.registers
        couple    = regs_to_int32(regs[0:2])/1000.0
        vitesse   = regs_to_int32(regs[2:4])/10
        puissance = regs_to_int32(regs[4:6])/100

        # Conversion puissance : valeur × 0.1 kW
        p_kw = puissance 

        self.live_vars["couple"].set(f"{couple}")
        self.live_vars["vitesse"].set(f"{vitesse}")
        self.live_vars["puissance"].set(f"{puissance:.1f}")

        # Historique
        self.history["couple"].append(float(couple))
        self.history["vitesse"].append(float(vitesse))
        self.history["puissance"].append(p_kw)
        self.t_elapsed += self.poll_interval.get()
        self.timestamps.append(self.t_elapsed)

    def _read_all_params(self):
        """Lit tous les registres de paramètres."""
        uid = self.slave_id.get()
        for name, addr in REGS.items():
            try:
                res = self.client.read_holding_registers(
                    address=addr, count=2, device_id=uid)
                if not res.isError():
                    val = regs_to_int32(res.registers)
                    self.reg_vars[name].set(str(val))
            except Exception:
                pass

    # ── Actions boutons ───────────────────────────────────────────────────

    def _read_all(self):
        if not self.connected:
            messagebox.showinfo("Info", "Veuillez d'abord vous connecter.")
            return
        try:
            self._read_live()
            self._read_all_params()
            self._log("📖 Lecture complète effectuée.")
        except Exception as e:
            self._log(f"❌ Erreur lecture : {e}")

    def _send_zero(self):
        """Remise à zéro via commande 05H (coil 0x0000 = FF 00)."""
        if not self.connected:
            messagebox.showinfo("Info", "Connectez-vous d'abord.")
            return
        if not messagebox.askyesno("Confirmer",
                "Effectuer une remise à zéro du couple ?"):
            return
        try:
            res = self.client.write_coil(
                address=0x0000, value=True, device_id=self.slave_id.get())
            if res.isError():
                self._log(f"⚠️  Erreur zéro : {res}")
            else:
                self._log("⭕ Remise à zéro effectuée.")
        except Exception as e:
            self._log(f"❌ Erreur : {e}")

    def _factory_reset(self):
        """Reset usine : écriture 0x00000001 via commande 10H."""
        if not self.connected:
            messagebox.showinfo("Info", "Connectez-vous d'abord.")
            return
        if not messagebox.askyesno("Confirmer",
                "⚠️  Restaurer les paramètres d'usine ?\n"
                "Toutes vos configurations seront effacées."):
            return
        try:
            # D'après le manuel : write 00 00 00 01 via 10H
            res = self.client.write_registers(
                address=0x06,
                values=[0x0000, 0x0001],
                device_id=self.slave_id.get())
            if res.isError():
                self._log(f"⚠️  Erreur reset usine : {res}")
            else:
                self._log("🏭 Reset usine envoyé.")
        except Exception as e:
            self._log(f"❌ Erreur : {e}")

    def _export_log(self):
        import datetime
        fname = f"dyn200_log_{datetime.datetime.now():%Y%m%d_%H%M%S}.txt"
        path = f"/mnt/user-data/outputs/{fname}"
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.log_lines))
            self._log(f"📋 Log exporté → {fname}")
        except Exception as e:
            self._log(f"❌ Export échoué : {e}")

    # ── Journal ───────────────────────────────────────────────────────────

    def _log(self, msg):
        import datetime
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        self.log_lines.append(line)
        self.log_box.configure(state="normal")
        self.log_box.insert("end", line + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # ── Fermeture ─────────────────────────────────────────────────────────

    def _on_close(self):
        self._disconnect()
        self.destroy()


# ─────────────────────────────────────────────────────────────────────────────
#  Mode démo (sans matériel)
# ─────────────────────────────────────────────────────────────────────────────

class DemoApp(DYN200App):
    """Version démo avec données simulées — pas besoin de matériel."""

    def __init__(self):
        super().__init__()
        self.title("DYN-200 — Interface MODBUS RTU  [MODE DÉMO]")
        self._log("ℹ️  Démarrage en MODE DÉMO (aucun capteur requis)")
        self._log("    Installez pymodbus + pyserial pour le matériel réel.")
        self._start_demo()

    def _start_demo(self):
        self._demo_t = 0.0
        self._run_demo()

    def _run_demo(self):
        import math, random
        t = self._demo_t
        couple    = 15.0 * math.sin(t * 0.5) + random.uniform(-0.3, 0.3)
        vitesse   = 1500 + 200 * math.sin(t * 0.3) + random.uniform(-5, 5)
        puissance = abs(couple * vitesse / 9550)

        self.live_vars["couple"].set(f"{couple:.2f}")
        self.live_vars["vitesse"].set(f"{vitesse:.0f}")
        self.live_vars["puissance"].set(f"{puissance:.3f}")

        self.history["couple"].append(couple)
        self.history["vitesse"].append(vitesse)
        self.history["puissance"].append(puissance)
        self.t_elapsed += 0.3
        self.timestamps.append(self.t_elapsed)

        self._demo_t += 0.3
        self.after(300, self._run_demo)


# ─────────────────────────────────────────────────────────────────────────────
#  Point d'entrée
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    demo_mode = (not HAS_MODBUS) or ("--demo" in sys.argv)

    if demo_mode:
        app = DemoApp()
    else:
        app = DYN200App()

    app.mainloop()
