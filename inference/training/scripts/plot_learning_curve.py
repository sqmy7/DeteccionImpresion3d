"""Grafica la curva de aprendizaje real a partir del results.csv de Ultralytics.

Uso: python plot_learning_curve.py RESULTS_CSV SALIDA_PNG
El results.csv queda en runs/final/<modelo>/results.csv (Colab) tras el entrenamiento.
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def main(csv_path, out_path):
    df = pd.read_csv(csv_path)
    df.columns = [c.strip() for c in df.columns]
    ep = df["epoch"]
    val_loss = df[["val/box_loss", "val/cls_loss", "val/dfl_loss"]].sum(axis=1)
    train_loss = df[["train/box_loss", "train/cls_loss", "train/dfl_loss"]].sum(axis=1)
    best = int(val_loss.idxmin())

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(8, 8), sharex=True)
    a1.plot(ep, train_loss, color="#1f77b4", label="entrenamiento")
    a1.plot(ep, val_loss, color="#ff7f0e", label="validación")
    a1.axvline(ep[best], ls="--", color="gray", label=f"mejor época ({int(ep[best])})")
    a1.set(ylabel="Pérdida (box+cls+dfl)", title="Pérdida por época")
    a1.legend()

    a2.plot(ep, df["metrics/mAP50(B)"], color="#2ca02c", label="mAP50")
    a2.plot(ep, df["metrics/mAP50-95(B)"], color="#9467bd", label="mAP50-95")
    a2.set(xlabel="Época", ylabel="mAP de validación", title="Rendimiento de validación por época")
    a2.legend()
    for a in (a1, a2):
        a.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_path, dpi=200)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
