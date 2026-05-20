from llm.extract_specs import process_product
import re

client = OpenAI()

# these are the specs that stayed consistently extractable across
# most sources after normalization/semantic mapping.
# generic retailer/manufacturer labels were too unstable for agreement scoring.
PILLARS = {
    "laptops": ["cpu_model", "ram_gb", "storage_gb", "weight_lb", "screen_brightness_nit", "display_resolution", "battery_life_hr"],
    "headphones": ["driver_type", "frequency_response_hz", "battery_life_hr", "impedance_ohms", "noise_cancellation"],
    "portable_power": ["capacity_mah", "power_w", "output_ports", "charging_speed_w"],
    "mini_fridges": ["total_capacity_cu_ft", "refrigerator_capacity_cu_ft", "freezer_capacity_cu_ft", "noise_db", "energy_star_certified"],
    "air_fryers": ["capacity_qt", "basket_material", "power_w", "max_temperature_f"],
    "espresso": ["pump_pressure_bar", "power_w", "heating_system", "water_tank_capacity_oz"]
}

def clean_price(p):
    if not p:
        return None
    p = str(p)
    p = re.sub(r"[^\d.]", "", p)
    try:
        return float(p)
    except Exception:
        return None

def get_pillar_count(structured, category):
    pillar_keys = PILLARS.get(category, [])
    return sum(1 for k, _ in structured if k in pillar_keys)