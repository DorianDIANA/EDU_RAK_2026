#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
Calculateur de Dimensionnement pour le PMIC Texas Instruments BQ25570
Energy Harvesting, Gestion Batterie/Supercondensateur & Sortie Buck ULP
================================================================================
Auteur  : Master 2 Électronique & Systèmes Embarqués
Usage   : 
    - Ligne de commande interactive : python3 bq25570_calculator.py
    - Avec arguments : python3 bq25570_calculator.py --vbat-ov 4.0 --vout 3.3 --supercap 10.0
    - Module Python  : from bq25570_calculator import BQ25570Calculator
================================================================================
"""

import argparse
import math
from typing import Dict, Tuple, List, Optional

# Base des valeurs normalisées de la série E96 (tolérance 1%)
E96_BASE = [
    1.00, 1.02, 1.05, 1.07, 1.10, 1.13, 1.15, 1.18, 1.21, 1.24, 1.27, 1.30,
    1.33, 1.37, 1.40, 1.43, 1.47, 1.50, 1.54, 1.58, 1.62, 1.65, 1.69, 1.74,
    1.78, 1.82, 1.87, 1.91, 1.96, 2.00, 2.05, 2.10, 2.15, 2.21, 2.26, 2.32,
    2.37, 2.43, 2.49, 2.55, 2.61, 2.67, 2.74, 2.80, 2.87, 2.94, 3.01, 3.09,
    3.16, 3.24, 3.32, 3.40, 3.48, 3.57, 3.65, 3.74, 3.83, 3.92, 4.02, 4.12,
    4.22, 4.32, 4.42, 4.53, 4.64, 4.75, 4.87, 4.99, 5.11, 5.23, 5.36, 5.49,
    5.62, 5.76, 5.90, 6.04, 6.19, 6.34, 6.49, 6.65, 6.81, 6.98, 7.15, 7.32,
    7.50, 7.68, 7.87, 8.06, 8.25, 8.45, 8.66, 8.87, 9.09, 9.31, 9.53, 9.76
]

def generate_e96_range(min_val: float = 10e3, max_val: float = 25e6) -> List[float]:
    """Génère la liste des résistances normalisées E96 entre min_val et max_val en Ohms."""
    resistors = []
    decade_min = math.floor(math.log10(min_val))
    decade_max = math.ceil(math.log10(max_val))
    for dec in range(decade_min, decade_max + 1):
        mult = 10 ** dec
        for base in E96_BASE:
            val = round(base * mult, 2)
            if min_val <= val <= max_val:
                resistors.append(val)
    return sorted(list(set(resistors)))

E96_RESISTORS = generate_e96_range(10e3, 25e6)

def find_nearest_e96(val: float) -> float:
    """Trouve la valeur normalisée E96 la plus proche."""
    return min(E96_RESISTORS, key=lambda r: abs(r - val))

def format_res(res_ohms: float) -> str:
    """Formate une valeur de résistance en notation ingénieur lisible (kΩ, MΩ)."""
    if res_ohms >= 1e6:
        return f"{res_ohms / 1e6:.3f} MΩ"
    elif res_ohms >= 1e3:
        return f"{res_ohms / 1e3:.2f} kΩ"
    else:
        return f"{res_ohms:.2f} Ω"


class BQ25570Calculator:
    """
    Gestionnaire de dimensionnement analytique pour le TI BQ25570.
    Tension de référence interne : V_REF_DC = VBIAS = 1.21 V (typique).
    """
    V_REF_DC = 1.21  # Volts (Bandgap Reference)

    def __init__(self, r_sum_target: float = 13.0e6):
        """
        :param r_sum_target: Somme cible d'un pont diviseur (recommandé datasheet : 13 MΩ).
        """
        self.r_sum_target = r_sum_target

    def calculate_mppt(self, k_pv: float = 0.80) -> Dict:
        """
        Calcule les résistances ROC1 et ROC2 pour le ratio MPPT :
        V_MPP / V_OC = ROC1 / (ROC1 + ROC2) = k_pv
        """
        r_oc1_theo = k_pv * self.r_sum_target
        r_oc2_theo = self.r_sum_target - r_oc1_theo

        r_oc1_e96 = find_nearest_e96(r_oc1_theo)
        r_oc2_e96 = find_nearest_e96(r_oc2_theo)

        k_pv_reel = r_oc1_e96 / (r_oc1_e96 + r_oc2_e96)
        erreur_pct = ((k_pv_reel - k_pv) / k_pv) * 100.0

        return {
            "ROC1_theo": r_oc1_theo,
            "ROC2_theo": r_oc2_theo,
            "ROC1_E96": r_oc1_e96,
            "ROC2_E96": r_oc2_e96,
            "R_TOTAL": r_oc1_e96 + r_oc2_e96,
            "k_pv_cible": k_pv,
            "k_pv_reel": k_pv_reel,
            "erreur_pct": erreur_pct
        }

    def calculate_vbat_ov(self, vbat_ov_target: float = 4.00) -> Dict:
        """
        Calcule ROV1 et ROV2 pour le seuil de surtension :
        V_BAT_OV = (3/2) * V_REF_DC * (1 + ROV2 / ROV1)
        """
        v_ov_bias = 1.5 * self.V_REF_DC  # 1.815 V
        if vbat_ov_target <= v_ov_bias:
            raise ValueError(f"VBAT_OV ({vbat_ov_target}V) doit être strictement supérieur à 1.5 * V_REF ({v_ov_bias}V)")

        ratio = (vbat_ov_target / v_ov_bias) - 1.0
        r_ov1_theo = self.r_sum_target / (1.0 + ratio)
        r_ov2_theo = ratio * r_ov1_theo

        # Recherche de la meilleure paire E96 proche de r_sum_target (10-16 MΩ)
        best_pair = None
        min_score = float("inf")
        for r1 in E96_RESISTORS:
            if 3.0e6 <= r1 <= 9.0e6:
                r2 = find_nearest_e96(ratio * r1)
                r_sum = r1 + r2
                v_calc = v_ov_bias * (1.0 + r2 / r1)
                err_v = abs(v_calc - vbat_ov_target) / vbat_ov_target
                err_sum = abs(r_sum - self.r_sum_target) / self.r_sum_target
                score = err_v * 10.0 + err_sum
                if score < min_score:
                    min_score = score
                    best_pair = (r1, r2, v_calc)

        r_ov1_e96, r_ov2_e96, vbat_ov_reel = best_pair
        erreur_pct = ((vbat_ov_reel - vbat_ov_target) / vbat_ov_target) * 100.0

        return {
            "ROV1_theo": r_ov1_theo,
            "ROV2_theo": r_ov2_theo,
            "ROV1_E96": r_ov1_e96,
            "ROV2_E96": r_ov2_e96,
            "R_TOTAL": r_ov1_e96 + r_ov2_e96,
            "VBAT_OV_cible": vbat_ov_target,
            "VBAT_OV_reel": vbat_ov_reel,
            "erreur_pct": erreur_pct
        }

    def calculate_vbat_uv(self, vbat_uv_target: float = 2.00) -> Dict:
        """
        Calcule RUV1 et RUV2 pour le seuil de sous-tension :
        V_BAT_UV = V_REF_DC * (1 + RUV2 / RUV1)
        """
        if vbat_uv_target <= self.V_REF_DC:
            raise ValueError(f"VBAT_UV ({vbat_uv_target}V) doit être strictement supérieur à V_REF ({self.V_REF_DC}V)")

        ratio = (vbat_uv_target / self.V_REF_DC) - 1.0
        r_uv1_theo = self.r_sum_target / (1.0 + ratio)
        r_uv2_theo = ratio * r_uv1_theo

        best_pair = None
        min_score = float("inf")
        for r1 in E96_RESISTORS:
            if 4.0e6 <= r1 <= 10.0e6:
                r2 = find_nearest_e96(ratio * r1)
                r_sum = r1 + r2
                v_calc = self.V_REF_DC * (1.0 + r2 / r1)
                err_v = abs(v_calc - vbat_uv_target) / vbat_uv_target
                err_sum = abs(r_sum - self.r_sum_target) / self.r_sum_target
                score = err_v * 10.0 + err_sum
                if score < min_score:
                    min_score = score
                    best_pair = (r1, r2, v_calc)

        r_uv1_e96, r_uv2_e96, vbat_uv_reel = best_pair
        erreur_pct = ((vbat_uv_reel - vbat_uv_target) / vbat_uv_target) * 100.0

        return {
            "RUV1_theo": r_uv1_theo,
            "RUV2_theo": r_uv2_theo,
            "RUV1_E96": r_uv1_e96,
            "RUV2_E96": r_uv2_e96,
            "R_TOTAL": r_uv1_e96 + r_uv2_e96,
            "VBAT_UV_cible": vbat_uv_target,
            "VBAT_UV_reel": vbat_uv_reel,
            "erreur_pct": erreur_pct
        }

    def calculate_vout(self, vout_target: float = 3.30) -> Dict:
        """
        Calcule ROUT1 et ROUT2 pour la sortie Buck :
        V_OUT = V_REF_DC * (1 + ROUT2 / ROUT1)
        """
        if vout_target <= self.V_REF_DC:
            raise ValueError(f"VOUT ({vout_target}V) doit être supérieur à V_REF ({self.V_REF_DC}V)")

        ratio = (vout_target / self.V_REF_DC) - 1.0
        r_out1_theo = self.r_sum_target / (1.0 + ratio)
        r_out2_theo = ratio * r_out1_theo

        best_pair = None
        min_score = float("inf")
        for r1 in E96_RESISTORS:
            if 3.0e6 <= r1 <= 8.0e6:
                r2 = find_nearest_e96(ratio * r1)
                r_sum = r1 + r2
                v_calc = self.V_REF_DC * (1.0 + r2 / r1)
                err_v = abs(v_calc - vout_target) / vout_target
                err_sum = abs(r_sum - self.r_sum_target) / self.r_sum_target
                score = err_v * 10.0 + err_sum
                if score < min_score:
                    min_score = score
                    best_pair = (r1, r2, v_calc)

        r_out1_e96, r_out2_e96, vout_reel = best_pair
        erreur_pct = ((vout_reel - vout_target) / vout_target) * 100.0

        return {
            "ROUT1_theo": r_out1_theo,
            "ROUT2_theo": r_out2_theo,
            "ROUT1_E96": r_out1_e96,
            "ROUT2_E96": r_out2_e96,
            "R_TOTAL": r_out1_e96 + r_out2_e96,
            "VOUT_cible": vout_target,
            "VOUT_reel": vout_reel,
            "erreur_pct": erreur_pct
        }

    def calculate_vbat_ok(self, vbat_ok_prog: float = 3.60, vbat_ok_hyst: float = 3.40) -> Dict:
        """
        Calcule ROK1, ROK2, ROK3 pour l'indicateur VBAT_OK avec hystérésis (TI Datasheet eq. 13 & 14):
        - Montée (Réveil haut)   : VBAT_OK_HYST = V_BIAS * (1 + (ROK2 + ROK3) / ROK1) = V_BIAS * RSUM / ROK1
        - Descente (Alerte basse) : VBAT_OK_PROG = V_BIAS * (1 + ROK2 / ROK1)
        """
        # Dans la notation TI :
        # v_high = Seuil haut (réveil)
        # v_low  = Seuil bas (alerte)
        v_high = max(vbat_ok_prog, vbat_ok_hyst)
        v_low  = min(vbat_ok_prog, vbat_ok_hyst)

        if not (v_high > v_low > self.V_REF_DC):
            raise ValueError(f"On doit avoir V_HIGH ({v_high}V) > V_LOW ({v_low}V) > V_REF ({self.V_REF_DC}V)")

        r_ok1_theo = (self.V_REF_DC / v_high) * self.r_sum_target
        r_ok2_theo = ((v_low / self.V_REF_DC) - 1.0) * r_ok1_theo
        r_ok3_theo = self.r_sum_target - r_ok1_theo - r_ok2_theo

        r_ok1_e96 = find_nearest_e96(r_ok1_theo)
        r_ok2_e96 = find_nearest_e96(r_ok2_theo)
        r_ok3_e96 = find_nearest_e96(r_ok3_theo)

        v_high_reel = self.V_REF_DC * (1.0 + (r_ok2_e96 + r_ok3_e96) / r_ok1_e96)
        v_low_reel  = self.V_REF_DC * (1.0 + r_ok2_e96 / r_ok1_e96)

        return {
            "ROK1_theo": r_ok1_theo,
            "ROK2_theo": r_ok2_theo,
            "ROK3_theo": r_ok3_theo,
            "ROK1_E96": r_ok1_e96,
            "ROK2_E96": r_ok2_e96,
            "ROK3_E96": r_ok3_e96,
            "R_TOTAL": r_ok1_e96 + r_ok2_e96 + r_ok3_e96,
            "V_HIGH_cible": v_high,
            "V_HIGH_reel": v_high_reel,
            "V_LOW_cible": v_low,
            "V_LOW_reel": v_low_reel
        }

    @staticmethod
    def calculate_energy_autonomy(
        c_farad: float = 10.0,
        v_max: float = 4.00,
        v_min: float = 2.00,
        p_sleep_watts: float = 10.0e-6,
        e_tx_joules: float = 15.0e-3,
        tx_period_seconds: float = 600.0,
        eta_buck: float = 0.85
    ) -> Dict:
        """
        Calcule l'énergie stockée dans le supercondensateur et l'autonomie en obscurité.
        """
        delta_e = 0.5 * c_farad * (v_max**2 - v_min**2)
        p_tx_moy = e_tx_joules / tx_period_seconds
        p_charge_moy = p_sleep_watts + p_tx_moy
        p_in_supercap = p_charge_moy / eta_buck

        t_secondes_actif = delta_e / p_in_supercap
        t_jours_actif = t_secondes_actif / 86400.0

        p_in_veille = p_sleep_watts / eta_buck
        t_secondes_veille = delta_e / p_in_veille
        t_jours_veille = t_secondes_veille / 86400.0

        return {
            "capacite_F": c_farad,
            "delta_E_joules": delta_e,
            "P_sleep_W": p_sleep_watts,
            "E_tx_J": e_tx_joules,
            "T_tx_s": tx_period_seconds,
            "P_tx_moy_W": p_tx_moy,
            "P_charge_totale_W": p_charge_moy,
            "P_prelevee_W": p_in_supercap,
            "autonomie_secondes": t_secondes_actif,
            "autonomie_jours": t_jours_actif,
            "autonomie_veille_jours": t_jours_veille
        }


def print_full_report(calc: BQ25570Calculator, k_pv: float, v_ov: float, v_uv: float, v_out: float,
                      v_ok_high: float, v_ok_low: float, supercap_f: float):
    """Affiche un rapport complet de calcul dans le terminal."""
    mppt = calc.calculate_mppt(k_pv)
    ov = calc.calculate_vbat_ov(v_ov)
    uv = calc.calculate_vbat_uv(v_uv)
    out = calc.calculate_vout(v_out)
    ok = calc.calculate_vbat_ok(v_ok_high, v_ok_low)
    auton = calc.calculate_energy_autonomy(c_farad=supercap_f, v_max=v_ov, v_min=v_uv)

    print("=" * 80)
    print(f" RAPPORT DE DIMENSIONNEMENT DU PMIC TI BQ25570 (Série E96 1%)")
    print(f" Tension de référence interne V_REF_DC = {calc.V_REF_DC:.2f} V | Somme cible ponts ≈ {calc.r_sum_target/1e6:.1f} MΩ")
    print("=" * 80)

    print("\n1. ÉCHANTILLONNAGE MPPT SOLAIRE (Broche VOC_SAMP)")
    print(f"   • Ratio MPPT Cible       : {mppt['k_pv_cible']*100:.1f} % de VOC")
    print(f"   • ROC1 Théorique / E96   : {format_res(mppt['ROC1_theo']):>11}  -->  {format_res(mppt['ROC1_E96']):>11} (E96)")
    print(f"   • ROC2 Théorique / E96   : {format_res(mppt['ROC2_theo']):>11}  -->  {format_res(mppt['ROC2_E96']):>11} (E96)")
    print(f"   • Ratio Réel Obtenu      : {mppt['k_pv_reel']*100:.2f} % (Erreur: {mppt['erreur_pct']:+.2f} %)")
    print(f"   • Somme Totale du Pont   : {format_res(mppt['R_TOTAL'])}")

    print("\n2. PROTECTION SURTENSION BATTERIE / SUPERCAP (VBAT_OV)")
    print(f"   • Seuil Cible (V_BAT_OV) : {ov['VBAT_OV_cible']:.2f} V")
    print(f"   • ROV1 Théorique / E96   : {format_res(ov['ROV1_theo']):>11}  -->  {format_res(ov['ROV1_E96']):>11} (E96)")
    print(f"   • ROV2 Théorique / E96   : {format_res(ov['ROV2_theo']):>11}  -->  {format_res(ov['ROV2_E96']):>11} (E96)")
    print(f"   • Seuil Réel Obtenu      : {ov['VBAT_OV_reel']:.3f} V (Erreur: {ov['erreur_pct']:+.2f} %)")
    print(f"   • Somme Totale du Pont   : {format_res(ov['R_TOTAL'])}")

    print("\n3. PROTECTION SOUS-TENSION BATTERIE / SUPERCAP (VBAT_UV)")
    print(f"   • Seuil Cible (V_BAT_UV) : {uv['VBAT_UV_cible']:.2f} V")
    print(f"   • RUV1 Théorique / E96   : {format_res(uv['RUV1_theo']):>11}  -->  {format_res(uv['RUV1_E96']):>11} (E96)")
    print(f"   • RUV2 Théorique / E96   : {format_res(uv['RUV2_theo']):>11}  -->  {format_res(uv['RUV2_E96']):>11} (E96)")
    print(f"   • Seuil Réel Obtenu      : {uv['VBAT_UV_reel']:.3f} V (Erreur: {uv['erreur_pct']:+.2f} %)")
    print(f"   • Somme Totale du Pont   : {format_res(uv['R_TOTAL'])}")

    print("\n4. TENSION DE SORTIE RÉGULÉE BUCK (VOUT)")
    print(f"   • Tension Cible (V_OUT)  : {out['VOUT_cible']:.2f} V")
    print(f"   • ROUT1 Théorique / E96  : {format_res(out['ROUT1_theo']):>11}  -->  {format_res(out['ROUT1_E96']):>11} (E96)")
    print(f"   • ROUT2 Théorique / E96  : {format_res(out['ROUT2_theo']):>11}  -->  {format_res(out['ROUT2_E96']):>11} (E96)")
    print(f"   • Tension Réelle Obtenue : {out['VOUT_reel']:.3f} V (Erreur: {out['erreur_pct']:+.2f} %)")
    print(f"   • Somme Totale du Pont   : {format_res(out['R_TOTAL'])}")

    print("\n5. INDICATEUR DE DISPONIBILITÉ SYSTÈME (VBAT_OK & HYSTÉRÉSIS)")
    print(f"   • Réveil Cible / Obtenu  : {ok['V_HIGH_cible']:.2f} V  -->  {ok['V_HIGH_reel']:.3f} V")
    print(f"   • Alerte Cible / Obtenue : {ok['V_LOW_cible']:.2f} V  -->  {ok['V_LOW_reel']:.3f} V")
    print(f"   • ROK1 E96               : {format_res(ok['ROK1_E96']):>11}")
    print(f"   • ROK2 E96               : {format_res(ok['ROK2_E96']):>11}")
    print(f"   • ROK3 E96               : {format_res(ok['ROK3_E96']):>11}")
    print(f"   • Somme Totale du Pont   : {format_res(ok['R_TOTAL'])}")

    print("\n6. COMPOSANTS PASSIFS RECOMMANDÉS")
    print(f"   • L_BST (Boost Harvester): 22 µH  (DCR < 1.5 Ω, Isat > 150 mA - ex: Coilcraft LPS3015-223)")
    print(f"   • L_OUT (Buck Synchrone) : 10 µH  (DCR < 1.0 Ω, Isat > 200 mA - ex: Murata LQH3NPN100)")
    print(f"   • C_STOR (Réservoir int.): 4.7 µF (Céramique X7R 10V, placé au plus près de VSTOR)")
    print(f"   • C_OUT (Découplage Buck): 22 µF  (Céramique X7R 6.3V)")
    print(f"   • C_REF (Mémoire MPPT)   : 10 nF à 22 nF (C0G/NPO ultra-faible fuite)")

    print("\n7. BILAN ÉNERGÉTIQUE & AUTONOMIE DU SUPERCONDENSATEUR")
    print(f"   • Capacité Réservoir     : {auton['capacite_F']:.1f} Farads (Plage utile : {v_ov:.2f} V -> {v_uv:.2f} V)")
    print(f"   • Énergie Utile Stockée  : {auton['delta_E_joules']:.2f} Joules ({auton['delta_E_joules']/3.6:.2f} mWh)")
    print(f"   • Consommation Veille    : {auton['P_sleep_W']*1e6:.1f} µW")
    print(f"   • Tx Radio LoRaWAN       : {auton['E_tx_J']*1e3:.1f} mJ toutes les {auton['T_tx_s']/60:.0f} min (P_moy = {auton['P_tx_moy_W']*1e6:.1f} µW)")
    print(f"   • Puissance Totale Prév. : {auton['P_prelevee_W']*1e6:.2f} µW (avec rendement Buck 85%)")
    print(f"   • Autonomie en Émission  : {auton['autonomie_jours']:.1f} jours d'obscurité totale !")
    print(f"   • Autonomie en Veille    : {auton['autonomie_veille_jours']:.1f} jours")
    print("=" * 80)


def prompt_value(prompt_text: str, default_val: float, min_val: Optional[float] = None, max_val: Optional[float] = None, unit: str = "") -> float:
    """Demande interactivement une valeur à l'utilisateur avec validation."""
    unit_str = f" {unit}" if unit else ""
    while True:
        try:
            user_input = input(f" 👉 {prompt_text} [Défaut : {default_val}{unit_str}] : ").strip()
            if not user_input:
                return default_val
            val = float(user_input.replace(",", "."))
            if min_val is not None and val < min_val:
                print(f"    ⚠️ Erreur : La valeur doit être >= {min_val}{unit_str}. Réessayez.")
                continue
            if max_val is not None and val > max_val:
                print(f"    ⚠️ Erreur : La valeur doit être <= {max_val}{unit_str}. Réessayez.")
                continue
            return val
        except ValueError:
            print("    ⚠️ Erreur : Veuillez entrer un nombre valide.")


def interactive_mode():
    """Mode interactif pas-à-pas pour demander toutes les tensions souhaitées à l'utilisateur."""
    print("=" * 80)
    print("  🔧 CONFIGURATION INTERACTIVE DU PMIC TEXAS INSTRUMENTS BQ25570")
    print("  (Appuyez sur [Entrée] pour accepter la valeur par défaut entre crochets)")
    print("=" * 80)

    print("\n--- 1. ÉLÉMENT DE STOCKAGE (Batterie / Supercondensateur) ---")
    v_ov = prompt_value(
        "Tension maximale de surtension (VBAT_OV)",
        default_val=4.00,
        min_val=1.85,
        max_val=5.50,
        unit="V"
    )
    v_uv = prompt_value(
        "Tension minimale de sous-tension (VBAT_UV)",
        default_val=2.00,
        min_val=1.22,
        max_val=v_ov - 0.1,
        unit="V"
    )
    supercap_f = prompt_value(
        "Capacité du supercondensateur / réservoir",
        default_val=10.0,
        min_val=0.001,
        max_val=1000.0,
        unit="F"
    )

    print("\n--- 2. TENSION DE SORTIE RÉGULÉE (BUCK CONVERTER) ---")
    v_out = prompt_value(
        "Tension de sortie régulée VOUT pour la charge utile",
        default_val=3.30,
        min_val=1.30,
        max_val=v_ov,
        unit="V"
    )

    print("\n--- 3. SOURCE DE RÉCOLTE D'ÉNERGIE (MPPT) ---")
    print("   Options courantes : [1] Solaire Silicium (80%), [2] TEG Seebeck (50%), [3] Valeur personnalisée")
    choix = input("   Votre choix (1/2/3 ou Entrée pour 80%) [1] : ").strip()
    if choix == "2":
        k_pv = 0.50
    elif choix == "3":
        k_pv_input = prompt_value("Ratio MPPT V_MPP / V_OC en %", default_val=80.0, min_val=10.0, max_val=99.0, unit="%")
        k_pv = k_pv_input / 100.0
    else:
        k_pv = 0.80

    print("\n--- 4. SURVEILLANCE & DISPONIBILITÉ (VBAT_OK) ---")
    # Proposer des valeurs cohérentes avec VBAT_OV et VBAT_UV
    default_ok_high = round(min(v_ov * 0.90, max(v_out + 0.3, v_uv + 1.0)), 2)
    default_ok_low = round(min(default_ok_high - 0.20, max(v_out + 0.1, v_uv + 0.5)), 2)
    if default_ok_high <= default_ok_low:
        default_ok_high = 3.60
        default_ok_low = 3.40

    v_ok_high = prompt_value(
        "Seuil de réveil système à la montée (VBAT_OK_HIGH)",
        default_val=default_ok_high,
        min_val=v_uv + 0.1,
        max_val=v_ov,
        unit="V"
    )
    v_ok_low = prompt_value(
        "Seuil d'alerte / coupure à la descente (VBAT_OK_LOW)",
        default_val=default_ok_low,
        min_val=1.22,
        max_val=v_ok_high - 0.05,
        unit="V"
    )

    calc = BQ25570Calculator(r_sum_target=13.0e6)
    print("\nCalcul des résistances optimales en cours...\n")
    print_full_report(
        calc=calc,
        k_pv=k_pv,
        v_ov=v_ov,
        v_uv=v_uv,
        v_out=v_out,
        v_ok_high=v_ok_high,
        v_ok_low=v_ok_low,
        supercap_f=supercap_f
    )


def main():
    import sys
    parser = argparse.ArgumentParser(description="Calculateur des résistances de réglage du PMIC TI BQ25570.")
    parser.add_argument("--interactive", "-i", action="store_true", help="Force le mode interactif pour saisir les tensions")
    parser.add_argument("--mppt", type=float, default=None, help="Ratio MPPT solaire (ex: 0.80 pour 80%%)")
    parser.add_argument("--vbat-ov", type=float, default=None, help="Tension de surtension max batterie/supercap (V)")
    parser.add_argument("--vbat-uv", type=float, default=None, help="Tension de sous-tension min batterie/supercap (V)")
    parser.add_argument("--vout", type=float, default=None, help="Tension de sortie régulée du Buck (V)")
    parser.add_argument("--vbat-ok-high", type=float, default=None, help="Seuil de réveil haut VBAT_OK (V)")
    parser.add_argument("--vbat-ok-low", type=float, default=None, help="Seuil d'alerte bas VBAT_OK (V)")
    parser.add_argument("--supercap", type=float, default=10.0, help="Capacité du supercondensateur en Farads")
    parser.add_argument("--r-sum", type=float, default=13.0e6, help="Somme cible de chaque pont diviseur en Ohms")

    args = parser.parse_args()

    # Si aucun argument de tension n'est passé en ligne de commande ou si -i est demandé : mode interactif
    has_cli_voltages = any([args.vbat_ov is not None, args.vbat_uv is not None, args.vout is not None, args.mppt is not None])

    if args.interactive or not has_cli_voltages:
        interactive_mode()
    else:
        k_pv = args.mppt if args.mppt is not None else 0.80
        v_ov = args.vbat_ov if args.vbat_ov is not None else 4.00
        v_uv = args.vbat_uv if args.vbat_uv is not None else 2.00
        v_out = args.vout if args.vout is not None else 3.30
        v_ok_high = args.vbat_ok_high if args.vbat_ok_high is not None else 3.60
        v_ok_low = args.vbat_ok_low if args.vbat_ok_low is not None else 3.40

        calc = BQ25570Calculator(r_sum_target=args.r_sum)
        print_full_report(
            calc=calc,
            k_pv=k_pv,
            v_ov=v_ov,
            v_uv=v_uv,
            v_out=v_out,
            v_ok_high=v_ok_high,
            v_ok_low=v_ok_low,
            supercap_f=args.supercap
        )

if __name__ == "__main__":
    main()

