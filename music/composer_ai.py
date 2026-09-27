from __future__ import annotations
import json, re, sys
from pathlib import Path

MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"

def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\\s*", "", text)
        text = re.sub(r"\\s*```$", "", text)
    a=text.find("{"); b=text.rfind("}")
    if a>=0 and b>a: text=text[a:b+1]
    return json.loads(text)

def main():
    inp=Path(sys.argv[1]); out=Path(sys.argv[2])
    payload=json.loads(inp.read_text(encoding="utf-8"))
    brief=str(payload.get("brief") or "").strip()
    project=payload.get("project") or {}
    from transformers import AutoTokenizer, AutoModelForCausalLM
    import torch
    tok=AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    model=AutoModelForCausalLM.from_pretrained(MODEL_ID, torch_dtype=torch.float32, low_cpu_mem_usage=True, trust_remote_code=True)
    model.eval()
    print("SC_COMPOSER_MODEL_READY", flush=True)
    system = """Jesteś profesjonalnym kompozytorem, songwriterem i producentem muzycznym. Projektujesz spójne piosenki, nie losowe frazy. Odpowiadasz WYŁĄCZNIE poprawnym JSON-em. Twórz po polsku, jeśli brief jest po polsku. Zasady: chwytliwy hook, sensowna dramaturgia, powtarzalny refren, podobna liczba sylab w liniach jednej sekcji, harmonia zgodna z tonacją, realistyczne BPM i długość. Nie kopiuj istniejących piosenek ani tekstów."""
    user = f"""Zaprojektuj kompletny utwór na podstawie briefu:\n{brief}\n\nAktualne ustawienia projektu: {json.dumps(project, ensure_ascii=False)}\n\nZwróć JSON o polach:\ntitle, language, duration_seconds (95-285), bpm (60-180), key, time_signature, style, chords, composer_hook, composer_structure, composer_notes, lyrics.\ncomposer_structure ma być czytelnym tekstem z sekcjami i liczbą taktów, np. Intro 8 | Verse 16 | Pre 8 | Chorus 16...\nchords ma zawierać osobne progresje dla Verse/Pre/Chorus/Bridge.\nlyrics ma używać nagłówków [Intro], [Verse 1], [Pre-Chorus], [Chorus], [Verse 2], [Bridge], [Final Chorus], [Outro]. Refren musi być rzeczywiście powtarzalny i zawierać composer_hook."""
    messages=[{"role":"system","content":system},{"role":"user","content":user}]
    text=tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs=tok([text], return_tensors="pt")
    with torch.no_grad():
        ids=model.generate(**inputs, max_new_tokens=1800, do_sample=True, temperature=0.72, top_p=0.9, repetition_penalty=1.08)
    out_text=tok.batch_decode(ids[:, inputs.input_ids.shape[1]:], skip_special_tokens=True)[0]
    data=_extract_json(out_text)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__": main()
