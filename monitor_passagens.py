#!/usr/bin/env python3
"""
Monitor de preços de passagens (Travelpayouts / Aviasales Data API, gratuita).
Guarda o histórico em historico_precos.csv (ideal para rodar no GitHub Actions).

Variáveis de ambiente: TP_TOKEN (obrigatória), TG_BOT_TOKEN e TG_CHAT_ID (opcionais).
Dependência: pip install requests
"""
import argparse
import csv
import os
import sys
from datetime import datetime

import requests

API_URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"
CSV_FILE = "historico_precos.csv"
CAMPOS = ["consultado_em", "origem", "destino", "ida", "volta",
          "preco", "companhia", "escalas", "link"]


def buscar_precos(token, origem, destino, mes, moeda):
    params = {
        "origin": origem, "destination": destino, "departure_at": mes,
        "currency": moeda, "sorting": "price", "limit": 30, "one_way": "false",
    }
    r = requests.get(API_URL, params=params,
                     headers={"X-Access-Token": token}, timeout=30)
    r.raise_for_status()
    return r.json().get("data", [])


def menor_preco_historico(origem, destino):
    if not os.path.exists(CSV_FILE):
        return None
    menor = None
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            if linha["origem"] == origem and linha["destino"] == destino:
                preco = float(linha["preco"])
                menor = preco if menor is None else min(menor, preco)
    return menor


def salvar(origem, destino, ofertas):
    novo = not os.path.exists(CSV_FILE)
    agora = datetime.now().isoformat(timespec="seconds")
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(CAMPOS)
        for o in ofertas:
            w.writerow([agora, origem, destino, o.get("departure_at"),
                        o.get("return_at"), o.get("price"), o.get("airline"),
                        o.get("transfers"), o.get("link")])


def avisar_telegram(texto):
    bot, chat = os.getenv("TG_BOT_TOKEN"), os.getenv("TG_CHAT_ID")
    if not (bot and chat):
        print("(Telegram não configurado)")
        return
    r = requests.post(f"https://api.telegram.org/bot{bot}/sendMessage",
                      data={"chat_id": chat, "text": texto}, timeout=30)
    print("Telegram:", "enviado" if r.ok else f"erro {r.status_code}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--origens", nargs="+", default=["GYN"])
    p.add_argument("--destino", default="ZNZ")
    p.add_argument("--meses", nargs="+", help="Meses de ida, formato YYYY-MM")
    p.add_argument("--alerta", type=float, help="Avisar abaixo deste valor")
    p.add_argument("--moeda", default="brl")
    p.add_argument("--teste-telegram", action="store_true",
                   help="Só envia uma mensagem de teste ao Telegram")
    a = p.parse_args()

    if a.teste_telegram:
        avisar_telegram("✅ Monitor de passagens conectado ao Telegram.")
        return
    if not (a.meses and a.alerta):
        sys.exit("Informe --meses e --alerta.")
    token = os.getenv("TP_TOKEN")
    if not token:
        sys.exit("Defina a variável de ambiente TP_TOKEN.")

    for origem in a.origens:
        anterior = menor_preco_historico(origem, a.destino)
        todas = []
        for mes in a.meses:
            try:
                ofertas = buscar_precos(token, origem, a.destino, mes, a.moeda)
            except requests.RequestException as e:
                print(f"Erro ao consultar {origem} {mes}: {e}")
                continue
            print(f"{origem}→{a.destino} {mes}: {len(ofertas)} ofertas em cache")
            salvar(origem, a.destino, ofertas)
            todas += ofertas

        if not todas:
            print(f"{origem}: nenhuma oferta em cache (rota de nicho pode vir vazia).")
            continue

        melhor = min(todas, key=lambda o: o["price"])
        msg = (f"{origem}→{a.destino}: {melhor['price']:.0f} {a.moeda.upper()} "
               f"({melhor.get('airline', '?')}, {melhor.get('transfers', '?')} escalas)\n"
               f"Ida: {(melhor.get('departure_at') or '')[:10]} | "
               f"Volta: {(melhor.get('return_at') or '')[:10]}\n"
               f"https://www.aviasales.com{melhor.get('link', '')}")
        print(msg)

        if melhor["price"] <= a.alerta:
            avisar_telegram("🎯 Abaixo do seu alvo!\n" + msg)
        elif anterior and melhor["price"] < anterior:
            avisar_telegram("📉 Novo menor preço histórico!\n" + msg)


if __name__ == "__main__":
    main()
