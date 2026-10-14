#!/usr/bin/env python3
"""Then vs Now — ek kurgular (2026-10-14, kullanıcı: kurgular 5 katı). tvn.py'deki 6 kurguya 24 yeni (toplam 30):

timeline, peak, realpeak, cheaper3, yearquiz, decades, birthyear, hundredbuys, tank, double, bigjump, bigdrop, flip,
higherlower, truefalse, top5, theme, dollar1, minwage, elecbill, coffeeyear, perunit, generations, spike

Sahneler: rec (tek fiş), pair (iki küçük fiş), multi (3-4 mini fiş), chart (yıllık fiyat çizgisi), opts (şıklar),
big (büyük rakam), bars (sıralama), tf (doğru/yanlış). Hepsi BLS ortalama fiyatları + CPI-U; uydurma rakam yok.
"""
import json
import subprocess

from PIL import Image, ImageDraw

import tvn
from tvn import (C, money, adj, latest, PRICES, SHORT, MINWAGE, CPI, font, ease, DISP, MONO, YEL, RED, GREEN, INK, FADED,
                 PAPER, W, H, FPS, SOURCE)

KURGU = ['timeline', 'peak', 'realpeak', 'cheaper3', 'yearquiz', 'decades', 'birthyear', 'hundredbuys', 'tank', 'double',
         'bigjump', 'bigdrop', 'flip', 'higherlower', 'truefalse', 'top5', 'theme', 'dollar1', 'minwage', 'elecbill',
         'coffeeyear', 'perunit', 'generations', 'spike']
ITEMS = [k for k in PRICES if PRICES[k]['years'] and k != 'oranges']
THEMES = {'breakfast': ['eggs', 'bacon', 'bread', 'coffee'], 'bbq': ['beef', 'chicken', 'tomatoes', 'bread'],
          'baking': ['eggs', 'sugar', 'milk', 'cheese'], 'dinner': ['chicken', 'rice', 'tomatoes', 'cheese'],
          'sandwich': ['bread', 'cheese', 'bacon', 'tomatoes']}
KWH = 863            # aylık ortalama konut tüketimi, EIA 2023
LAB = lambda k: SHORT[k]
NM = lambda k: PRICES[k]['phrase'][0].lower() + PRICES[k]['phrase'][1:]
NAME = lambda k: PRICES[k]['label'].split(',')[0].title()


def yrs(k): return sorted(PRICES[k]['years'])
def p(k, y): return PRICES[k]['years'][y]
def L(k): return latest(k)


def key_for(kg, rnd):
    it = rnd.choice(ITEMS)
    if kg in ('timeline', 'peak', 'realpeak', 'double', 'bigjump', 'bigdrop', 'decades', 'perunit'):
        if kg == 'double':
            y0 = rnd.choice([y for y in yrs(it) if y <= 2012]); return [kg, it, y0] if any(p(it, y) >= 2 * p(it, y0) for y in yrs(it) if y > y0) else None
        if kg == 'perunit' and it not in ('eggs', 'bread', 'electricity'): return None
        return [kg, it]
    if kg in ('cheaper3', 'top5', 'generations', 'yearquiz', 'birthyear', 'hundredbuys', 'spike'):
        y0 = rnd.choice(range(1995, 2016))
        if kg == 'cheaper3' and sum(p(k, L(k)) < adj(p(k, y0), y0, L(k)) for k in ITEMS if y0 in PRICES[k]['years']) < 3: return None
        if kg == 'hundredbuys': return [kg, y0, it]
        if kg == 'spike': return [kg, rnd.choice(range(1995, 2023))]
        return [kg, y0]
    if kg == 'flip':
        a, b = rnd.sample(ITEMS, 2); y0 = rnd.choice(range(1995, 2014))
        if y0 not in PRICES[a]['years'] or y0 not in PRICES[b]['years']: return None
        return [kg, a, b, y0] if (p(a, y0) < p(b, y0)) and (p(a, L(a)) > p(b, L(b))) else None
    if kg == 'higherlower':
        a, b = rnd.sample(ITEMS, 2); y0 = rnd.choice(range(1995, 2010))
        return [kg, a, b, y0] if y0 in PRICES[b]['years'] and 0.4 < p(a, L(a)) / p(b, y0) < 2.5 else None
    if kg == 'truefalse':
        y0 = rnd.choice([y for y in yrs(it) if y <= 2018]); return [kg, it, y0, rnd.choice([1.5, 2, 3])]
    if kg == 'theme': return [kg, rnd.choice(list(THEMES)), rnd.choice(range(1996, 2016))]
    if kg in ('dollar1', 'minwage'): return [kg, rnd.choice(range(1970 if kg == 'dollar1' else 1995, 2016))]
    if kg in ('tank', 'elecbill', 'coffeeyear'): return [kg, rnd.choice(range(1995, 2016))]
    return None


def build(key, rnd):
    kg = key[0]; B = []; src = SOURCE
    if kg == 'timeline':
        it = key[1]; ys = [y for y in yrs(it) if y % 5 == 0 or y == L(it)]
        B = [(C(rnd, f"{NM(it).capitalize()}, every five years since {ys[0]}. Watch the price.", f"Let's watch {NM(it)} climb, five years at a time."), dict(t='chart', it=it, n=1))]
        for i, y in enumerate(ys[1:], 2):
            B.append((f"{y}: {money(p(it, y))}.", dict(t='chart', it=it, n=i, ys=ys)))
        B.append((C(rnd, f"From {money(p(it, ys[0]))} to {money(p(it, ys[-1]))}. Which year do you remember?", "Which jump hurt the most? Comment below."), dict(t='chart', it=it, n=len(ys), ys=ys, cta='WHICH YEAR HURT?')))
        B[0][1]['ys'] = ys
        title = f"{NAME(it)} Prices Every 5 Years, {ys[0]} to {ys[-1]}"
    elif kg in ('peak', 'realpeak'):
        it = key[1]; ys = yrs(it); y1 = L(it)
        val = (lambda y: p(it, y)) if kg == 'peak' else (lambda y: adj(p(it, y), y, y1))
        pk = max(ys, key=val); lo = min(ys, key=val)
        what = 'the most expensive' if kg == 'peak' else 'the most expensive, adjusted for inflation'
        B = [(C(rnd, f"In which year was {NM(it)} {what}?", f"Guess the peak year for {NM(it)}{' in today’s dollars' if kg == 'realpeak' else ''}."), dict(t='chart', it=it, n=0, real=kg == 'realpeak')),
             ("Here is every year.", dict(t='chart', it=it, n=99, real=kg == 'realpeak', anim=True)),
             (f"The peak: {pk}, at {money(val(pk))}{' in today’s dollars' if kg == 'realpeak' else ''}.", dict(t='chart', it=it, n=99, real=kg == 'realpeak', mark=pk)),
             (f"The low point was {lo}, at {money(val(lo))}.", dict(t='chart', it=it, n=99, real=kg == 'realpeak', mark=pk, mark2=lo)),
             (C(rnd, "Did you guess the year? Comment below.", "What year should I check next? Comment below."), dict(t='chart', it=it, n=99, real=kg == 'realpeak', mark=pk, mark2=lo, cta='DID YOU GUESS IT?'))]
        title = f"The Year {NAME(it)} Prices Peaked{' (Adjusted for Inflation)' if kg == 'realpeak' else ''}"
    elif kg == 'cheaper3':
        y0 = key[1]; cand = [k for k in ITEMS if y0 in PRICES[k]['years'] and p(k, L(k)) < adj(p(k, y0), y0, L(k))]
        cand.sort(key=lambda k: p(k, L(k)) / adj(p(k, y0), y0, L(k))); three = cand[:3]
        rows = [dict(l=LAB(k), v=f"{(p(k, L(k)) / adj(p(k, y0), y0, L(k)) - 1) * 100:+.0f}%", w=1 - p(k, L(k)) / adj(p(k, y0), y0, L(k)), c=GREEN) for k in three]
        B = [(C(rnd, f"Three things that are actually cheaper than in {y0}, once you count inflation.", f"Not everything got more expensive since {y0}. Here are three that got cheaper in real terms."), dict(t='bars', rows=rows, n=0, head=f'CHEAPER THAN {y0}'))]
        for i, k in enumerate(three):
            B.append((f"{NM(k).capitalize()}: {money(p(k, y0))} in {y0}, {money(p(k, L(k)))} now. With inflation it should be {money(adj(p(k, y0), y0, L(k)))}.", dict(t='bars', rows=rows, n=i + 1, head=f'CHEAPER THAN {y0}')))
        B.append(("Which one surprised you? Comment below.", dict(t='bars', rows=rows, n=3, head=f'CHEAPER THAN {y0}', cta='SURPRISED?')))
        title = f"3 Things That Are Cheaper Than in {y0} (Adjusted for Inflation)"
    elif kg == 'yearquiz':
        y0 = key[1]; its = [k for k in ['eggs', 'bread', 'gas', 'milk', 'coffee', 'beef'] if y0 in PRICES[k]['years']][:3]
        opts = sorted({y0, max(1995, y0 - rnd.choice([4, 6, 8])), min(2024, y0 + rnd.choice([4, 6, 8]))})
        if len(opts) < 3: opts = [y0 - 5, y0, y0 + 5]
        r = opts.index(y0); lines = [(LAB(k), p(k, y0), '$') for k in its]
        B = [(C(rnd, "Guess the year from this receipt.", "What year is this receipt from?"), dict(t='rec', year='????', lines=lines)),
             (f"Is it {opts[0]}, {opts[1]}, or {opts[2]}?", dict(t='rec', year='????', lines=lines, opts=[str(o) for o in opts])),
             (f"It's {y0}.", dict(t='rec', year=y0, lines=lines, opts=[str(o) for o in opts], r=r)),
             (f"Today the same three cost {money(sum(p(k, L(k)) for k in its))}.", dict(t='rec', year=y0, lines=lines, opts=[str(o) for o in opts], r=r, now=sum(p(k, L(k)) for k in its))),
             ("Did you get the year? Comment below.", dict(t='rec', year=y0, lines=lines, opts=[str(o) for o in opts], r=r, cta='DID YOU GET IT?'))]
        title = "Guess the Year From This Grocery Receipt"
    elif kg in ('decades', 'generations'):
        if kg == 'decades':
            it = key[1]; ys = [y for y in (1995, 2005, 2015, L(it)) if y in PRICES[it]['years']]
            cards = [dict(y=y, l=LAB(it), v=p(it, y)) for y in ys]
            hook = C(rnd, f"{NM(it).capitalize()} across three decades.", f"Same {NAME(it).lower()}, four snapshots: {', '.join(map(str, ys))}.")
            title = f"{NAME(it)}: {', '.join(map(str, ys))}"
        else:
            y0 = key[1]; mid = (y0 + 2025) // 2; its = [k for k in ['eggs', 'bread', 'milk', 'coffee'] if y0 in PRICES[k]['years']]
            ys = [y0, mid, min(L(k) for k in its)]
            cards = [dict(y=y, l='4 GROCERIES', v=sum(p(k, y) for k in its)) for y in ys]
            hook = f"Three generations, one shopping list: {', '.join(NAME(k).lower() for k in its)}."
            title = f"The Same 4 Groceries in {ys[0]}, {ys[1]} and {ys[2]}"
        B = [(hook + f" {cards[0]['y']}: {money(cards[0]['v'])}.", dict(t='multi', cards=cards, n=1))]
        for i in range(1, len(cards)):
            B.append((f"{cards[i]['y']}: {money(cards[i]['v'])}.", dict(t='multi', cards=cards, n=i + 1)))
        B.append((f"That's {(cards[-1]['v'] / cards[0]['v'] - 1) * 100:.0f} percent more than {cards[0]['y']}. Which year did you shop in? Comment below.", dict(t='multi', cards=cards, n=len(cards), cta='WHICH YEAR?')))
    elif kg == 'birthyear':
        y0 = key[1]; its = [k for k in ['eggs', 'gas', 'bread', 'coffee'] if y0 in PRICES[k]['years']][:3]
        l0 = [(LAB(k), p(k, y0), '$') for k in its]; l1 = [(LAB(k), p(k, L(k)), '$') for k in its]
        B = [(C(rnd, f"Born in {y0}? Here's what things cost the year you were born.", f"If you were born in {y0}, this was your parents' receipt."), dict(t='rec', year=y0, lines=l0)),
             (', '.join(f"{NAME(k).lower()} {money(p(k, y0))}" for k in its) + '.', dict(t='rec', year=y0, lines=l0)),
             ("And now:", dict(t='pair', y0=y0, l0=l0, y1=min(L(k) for k in its), l1=l1)),
             (', '.join(f"{NAME(k).lower()} {money(p(k, L(k)))}" for k in its) + '.', dict(t='pair', y0=y0, l0=l0, y1=min(L(k) for k in its), l1=l1)),
             ("What year were you born? Comment and I might check it.", dict(t='pair', y0=y0, l0=l0, y1=min(L(k) for k in its), l1=l1, cta='YOUR BIRTH YEAR?'))]
        title = f"Born in {y0}? Here's What Things Cost"
    elif kg == 'hundredbuys':
        y0, it = key[1], key[2]
        if y0 not in PRICES[it]['years']: y0 = yrs(it)[0]
        n0, n1 = 100 / p(it, y0), 100 / p(it, L(it)); unit = SHORT[it].split('/')[-1].strip().lower()
        B = [(f"How much {NAME(it).lower()} did one hundred dollars buy in {y0}?", dict(t='big', top=f'$100 IN {y0}', v='?', sub=LAB(it))),
             (f"About {n0:,.0f} {unit}s.".replace('lbs', 'pounds').replace(' lbs', ' pounds').replace('lb', 'pound'), dict(t='big', top=f'$100 IN {y0}', v=f'{n0:,.0f}', sub=LAB(it), anim=True)),
             (f"Today, one hundred dollars buys {n1:,.0f} {unit}s.".replace('lbs', 'pounds').replace('lb', 'pound'), dict(t='big', top=f'$100 IN {L(it)}', v=f'{n1:,.0f}', sub=LAB(it), anim=True, red=True)),
             (f"That's {(1 - n1 / n0) * 100:.0f} percent less for the same bill." if n1 < n0 else f"That's actually more.", dict(t='big', top='DIFFERENCE', v=f'{(n1 / n0 - 1) * 100:+.0f}%', sub=LAB(it), red=True)),
             ("What would you buy with a hundred dollars? Comment below.", dict(t='big', top='DIFFERENCE', v=f'{(n1 / n0 - 1) * 100:+.0f}%', sub=LAB(it), red=True, cta='WHAT WOULD YOU BUY?'))]
        title = f"What $100 Bought in {NAME(it)}: {y0} vs Today"
    elif kg in ('tank', 'elecbill', 'coffeeyear'):
        y0 = key[1]
        if kg == 'tank':
            it, q, what = 'gas', 15, 'a 15 gallon tank of gas'
        elif kg == 'elecbill':
            it, q, what = 'electricity', KWH / 100, f'a month of electricity ({KWH} kilowatt hours)'
        else:
            it, q, what = 'coffee', 52, 'a pound of coffee every week for a year'
        y1 = L(it); c0, c1 = p(it, y0) * q, p(it, y1) * q; inf = adj(c0, y0, y1); m0, m1 = c0 / MINWAGE[y0], c1 / MINWAGE[y1]
        B = [(C(rnd, f"How much was {what} in {y0}?", f"{what.capitalize()}. {y0} versus today."), dict(t='big', top=f'{y0}', v='?', sub={'tank': '15 GALLON TANK', 'elecbill': f'{KWH} KWH / MONTH', 'coffeeyear': '1 LB A WEEK, 1 YEAR'}[kg])),
             (f"In {y0}: {money(c0)}.", dict(t='big', top=f'{y0}', v=money(c0), sub={'tank': '15 GALLON TANK', 'elecbill': f'{KWH} KWH / MONTH', 'coffeeyear': '1 LB A WEEK, 1 YEAR'}[kg], anim=True)),
             (f"Today: {money(c1)}.", dict(t='big', top=f'{y1}', v=money(c1), sub={'tank': '15 GALLON TANK', 'elecbill': f'{KWH} KWH / MONTH', 'coffeeyear': '1 LB A WEEK, 1 YEAR'}[kg], anim=True, red=True)),
             (f"With inflation alone it would be {money(inf)}. At the federal minimum wage that is {m0:.1f} hours of work then, and {m1:.1f} hours now.", dict(t='big', top='HOURS OF MIN WAGE', v=f'{m0:.1f} → {m1:.1f}'.replace('→', 'TO'), sub='THEN TO NOW')),
             ("What do you pay? Comment below.", dict(t='big', top=f'{y1}', v=money(c1), sub={'tank': '15 GALLON TANK', 'elecbill': f'{KWH} KWH / MONTH', 'coffeeyear': '1 LB A WEEK, 1 YEAR'}[kg], red=True, cta='WHAT DO YOU PAY?'))]
        title = {'tank': f"Filling Up a 15-Gallon Tank: {y0} vs Today ⛽", 'elecbill': f"Your Monthly Electric Bill: {y0} vs Today 💡", 'coffeeyear': f"A Year of Coffee: {y0} vs Today ☕"}[kg]
        if kg == 'elecbill': src += f'\nAverage residential use {KWH} kWh/month (U.S. EIA, 2023), held constant for both years.'
    elif kg == 'double':
        it, y0 = key[1], key[2]; yd = min(y for y in yrs(it) if y > y0 and p(it, y) >= 2 * p(it, y0))
        B = [(f"{NM(it).capitalize()} cost {money(p(it, y0))} in {y0}. How long until the price doubled?", dict(t='chart', it=it, n=0, from_=y0)),
             ("Watch the line.", dict(t='chart', it=it, n=99, from_=y0, anim=True, double=p(it, y0) * 2)),
             (f"It doubled by {yd}, at {money(p(it, yd))}. That took {yd - y0} years.", dict(t='chart', it=it, n=99, from_=y0, double=p(it, y0) * 2, mark=yd)),
             (f"Prices overall rose {(CPI[yd] / CPI[y0] - 1) * 100:.0f} percent in the same time.", dict(t='chart', it=it, n=99, from_=y0, double=p(it, y0) * 2, mark=yd)),
             ("Did you guess the year? Comment below.", dict(t='chart', it=it, n=99, from_=y0, double=p(it, y0) * 2, mark=yd, cta='HOW MANY YEARS?'))]
        title = f"How Long Did It Take {NAME(it)} Prices to Double Since {y0}?"
    elif kg in ('bigjump', 'bigdrop'):
        it = key[1]; ys = yrs(it); pairs = [(y, (p(it, y) / p(it, y - 1) - 1) * 100) for y in ys[1:] if y - 1 in PRICES[it]['years']]
        y, ch = (max if kg == 'bigjump' else min)(pairs, key=lambda x: x[1])
        if (kg == 'bigdrop' and ch >= 0) or (kg == 'bigjump' and ch <= 0): ch = 0
        B = [(C(rnd, f"What was the biggest one-year {'jump' if kg == 'bigjump' else 'drop'} in the price of {NM(it)}?", f"One year, one big {'shock' if kg == 'bigjump' else 'relief'}: {NAME(it).lower()}."), dict(t='chart', it=it, n=99)),
             (f"It happened in {y}.", dict(t='chart', it=it, n=99, mark=y)),
             (f"From {money(p(it, y - 1))} to {money(p(it, y))}, {'up' if ch >= 0 else 'down'} {abs(ch):.0f} percent in a single year.", dict(t='chart', it=it, n=99, mark=y, mark2=y - 1)),
             ("Do you remember that year? Comment below.", dict(t='chart', it=it, n=99, mark=y, mark2=y - 1, cta='REMEMBER IT?'))]
        title = f"The Biggest One-Year {'Jump' if kg == 'bigjump' else 'Drop'} in {NAME(it)} Prices"
    elif kg == 'flip':
        _, a, b, y0 = key
        l0 = [(LAB(a), p(a, y0), '$'), (LAB(b), p(b, y0), '$')]; y1 = min(L(a), L(b)); l1 = [(LAB(a), p(a, y1), '$'), (LAB(b), p(b, y1), '$')]
        B = [(f"In {y0}, {NM(a)} was cheaper than {NM(b)}.", dict(t='rec', year=y0, lines=l0)),
             (f"{money(p(a, y0))} versus {money(p(b, y0))}.", dict(t='rec', year=y0, lines=l0)),
             ("Today they switched places.", dict(t='pair', y0=y0, l0=l0, y1=y1, l1=l1)),
             (f"{NAME(a)}: {money(p(a, y1))}. {NAME(b)}: {money(p(b, y1))}.", dict(t='pair', y0=y0, l0=l0, y1=y1, l1=l1)),
             ("Did you notice? Comment below.", dict(t='pair', y0=y0, l0=l0, y1=y1, l1=l1, cta='DID YOU NOTICE?'))]
        title = f"{NAME(a)} Used to Be Cheaper Than {NAME(b)}. Not Anymore"
    elif kg == 'higherlower':
        _, a, b, y0 = key; pa, pb = p(a, L(a)), p(b, y0); hi = pa > pb
        B = [(f"Higher or lower? {NM(a).capitalize()} today, or {NM(b)} in {y0}?", dict(t='opts', top=f'{NAME(a).upper()} TODAY vs {NAME(b).upper()} {y0}', o=['TODAY IS HIGHER', 'TODAY IS LOWER'])),
             ("Pick one.", dict(t='opts', top=f'{NAME(a).upper()} TODAY vs {NAME(b).upper()} {y0}', o=['TODAY IS HIGHER', 'TODAY IS LOWER'])),
             (f"{NAME(a)} today: {money(pa)}. {NAME(b)} in {y0}: {money(pb)}.", dict(t='opts', top=f'{NAME(a).upper()} TODAY vs {NAME(b).upper()} {y0}', o=[money(pa), money(pb)])),
             (f"So today is {'higher' if hi else 'lower'}.", dict(t='opts', top=f'{NAME(a).upper()} TODAY vs {NAME(b).upper()} {y0}', o=['TODAY IS HIGHER', 'TODAY IS LOWER'], r=0 if hi else 1)),
             ("Did you get it? Comment higher or lower.", dict(t='opts', top=f'{NAME(a).upper()} TODAY vs {NAME(b).upper()} {y0}', o=['TODAY IS HIGHER', 'TODAY IS LOWER'], r=0 if hi else 1, cta='HIGHER OR LOWER?'))]
        title = f"Higher or Lower: {NAME(a)} Today vs {NAME(b)} in {y0}"
    elif kg == 'truefalse':
        _, it, y0, f = key; y1 = L(it); real = p(it, y1) / p(it, y0); tr = real >= f
        claim = f"{NM(it).capitalize()} costs at least {f:g} times what it did in {y0}."
        B = [(f"True or false? {claim}", dict(t='tf', q=claim)),
             ("Think about it.", dict(t='tf', q=claim)),
             (f"{'True' if tr else 'False'}. {money(p(it, y0))} then, {money(p(it, y1))} now: {real:.1f} times.", dict(t='tf', q=claim, r=0 if tr else 1)),
             ("Did you get it right? Comment true or false.", dict(t='tf', q=claim, r=0 if tr else 1, cta='TRUE OR FALSE?'))]
        title = f"True or False: {NAME(it)} Costs {f:g}x What It Did in {y0}"
    elif kg == 'top5':
        y0 = key[1]; its = [k for k in ITEMS if y0 in PRICES[k]['years']]
        ch = sorted(((k, (p(k, L(k)) / p(k, y0) - 1) * 100) for k in its), key=lambda x: -x[1])[:5][::-1]
        mx = max(c for _, c in ch)
        rows = [dict(l=LAB(k), v=f'{c:+.0f}%', w=c / mx, c=RED, r=5 - i) for i, (k, c) in enumerate(ch)]
        B = [(C(rnd, f"The five prices that rose the most since {y0}. Counting down.", f"Top five price jumps since {y0}."), dict(t='bars', rows=rows, n=0, head=f'TOP 5 SINCE {y0}'))]
        for i, (k, c) in enumerate(ch):
            B.append((f"Number {5 - i}: {NAME(k).lower()}, up {c:.0f} percent.", dict(t='bars', rows=rows, n=i + 1, head=f'TOP 5 SINCE {y0}')))
        B.append(("Which one do you feel the most? Comment below.", dict(t='bars', rows=rows, n=5, head=f'TOP 5 SINCE {y0}', cta='WHICH HURTS MOST?')))
        title = f"Top 5 Price Increases Since {y0}"
    elif kg == 'theme':
        _, th, y0 = key; its = [k for k in THEMES[th] if y0 in PRICES[k]['years']]; y1 = min(L(k) for k in its)
        l0 = [(LAB(k), p(k, y0), '$') for k in its]; l1 = [(LAB(k), p(k, y1), '$') for k in its]
        t0, t1 = sum(x for _, x, _ in l0), sum(x for _, x, _ in l1)
        nm = {'breakfast': 'a classic breakfast', 'bbq': 'a backyard barbecue', 'baking': 'a baking day', 'dinner': 'a chicken and rice dinner', 'sandwich': 'a bacon and cheese sandwich'}[th]
        B = [(f"The ingredients for {nm}, {y0} versus today.", dict(t='rec', year=y0, lines=l0)),
             (f"In {y0}: {money(t0)}.", dict(t='rec', year=y0, lines=l0)),
             (f"Today: {money(t1)}.", dict(t='pair', y0=y0, l0=l0, y1=y1, l1=l1)),
             (f"Up {(t1 / t0 - 1) * 100:.0f} percent. With inflation alone it would be {money(adj(t0, y0, y1))}.", dict(t='pair', y0=y0, l0=l0, y1=y1, l1=l1)),
             ("What do you cook most at home? Comment below.", dict(t='pair', y0=y0, l0=l0, y1=y1, l1=l1, cta='WHAT DO YOU COOK?'))]
        title = {'breakfast': 'Breakfast', 'bbq': 'A Backyard BBQ', 'baking': 'A Baking Day', 'dinner': 'Chicken and Rice Night', 'sandwich': 'A Bacon Cheese Sandwich'}[th] + f": {y0} Prices vs Today"
    elif kg == 'dollar1':
        y0 = key[1]; v = adj(1, y0, max(CPI)); eggs = p('eggs', L('eggs')) / 12
        B = [(f"One dollar from {y0}. What's it worth today?", dict(t='big', top=f'$1 IN {y0}', v='$1.00', sub='SAME BUYING POWER AS')),
             (f"{money(v)}.", dict(t='big', top=f'TODAY', v=money(v), sub='SAME BUYING POWER', anim=True, red=True)),
             (f"Flip it around: a dollar today buys what {100 / v:.0f} cents bought in {y0}.", dict(t='big', top=f'$1 TODAY = {y0}', v=f'{100 / v:.0f}¢'.replace('¢', ' CENTS'), sub='OF BUYING POWER')),
             (f"Today a dollar gets you about {1 / eggs:.1f} eggs.", dict(t='big', top='$1 TODAY', v=f'{1 / eggs:.1f} EGGS', sub='AT THE AVERAGE PRICE')),
             ("What year should I check next? Comment below.", dict(t='big', top='TODAY', v=money(v), sub='SAME BUYING POWER', red=True, cta='WHICH YEAR NEXT?'))]
        title = f"$1 From {y0} Is Worth This Today"
    elif kg == 'minwage':
        y0 = key[1]; w0 = MINWAGE[y0]; v = adj(w0, y0, max(CPI)); now = MINWAGE[max(MINWAGE)]
        B = [(f"The federal minimum wage in {y0} was {money(w0)} an hour. What is that in today's money?", dict(t='big', top=f'MIN WAGE {y0}', v=money(w0), sub='PER HOUR')),
             (f"{money(v)} an hour.", dict(t='big', top="IN TODAY'S DOLLARS", v=money(v), sub='PER HOUR', anim=True, red=True)),
             (f"The federal minimum today is {money(now)}. " + (f"That's {money(v - now)} less buying power per hour." if v > now else f"That's {money(now - v)} more."), dict(t='big', top='FEDERAL MIN TODAY', v=money(now), sub='PER HOUR')),
             ("Many states set a higher minimum. What's the minimum where you live? Comment below.", dict(t='big', top='FEDERAL MIN TODAY', v=money(now), sub='PER HOUR', cta='YOUR STATE MINIMUM?'))]
        title = f"The {y0} Minimum Wage in Today's Dollars"
        src += '\nFederal minimum wage: U.S. Department of Labor.'
    elif kg == 'perunit':
        it = key[1]; div, unit = {'eggs': (12, 'one egg'), 'bread': (16, 'one ounce of bread'), 'electricity': (100, 'one kilowatt hour'), 'gas': (1, 'one gallon of gas')}[it]
        y0 = yrs(it)[0]; y1 = L(it); c0, c1 = p(it, y0) / div * 100, p(it, y1) / div * 100
        B = [(f"How much was {unit} in {y0}?", dict(t='big', top=f'{unit.upper()} · {y0}', v='?', sub='IN CENTS')),
             (f"{c0:.1f} cents.", dict(t='big', top=f'{unit.upper()} · {y0}', v=f'{c0:.1f}¢'.replace('¢', ' C'), sub='IN CENTS', anim=True)),
             (f"Today: {c1:.1f} cents.", dict(t='big', top=f'{unit.upper()} · {y1}', v=f'{c1:.1f}¢'.replace('¢', ' C'), sub='IN CENTS', anim=True, red=True)),
             (f"That's {c1 / c0:.1f} times as much.", dict(t='big', top='TIMES AS MUCH', v=f'{c1 / c0:.1f}X', sub=unit.upper(), red=True)),
             ("Comment what you paid last time.", dict(t='big', top='TIMES AS MUCH', v=f'{c1 / c0:.1f}X', sub=unit.upper(), red=True, cta='WHAT DID YOU PAY?'))]
        title = f"The Price of {unit.replace('one ', 'One ').title().replace('Of', 'of')}: {y0} vs {y1}"
    else:                                       # spike: üç yıllık enflasyon
        y0 = key[1]; y3 = y0 + 3; r = (CPI[y3] / CPI[y0] - 1) * 100
        allr = sorted(((y, (CPI[y + 3] / CPI[y] - 1) * 100) for y in range(1995, 2023)), key=lambda x: -x[1]); rank = [y for y, _ in allr].index(y0) + 1
        B = [(f"How much did prices rise from {y0} to {y3}?", dict(t='big', top=f'{y0} TO {y3}', v='?', sub='ALL PRICES (CPI-U)')),
             (f"{r:.1f} percent in three years.", dict(t='big', top=f'{y0} TO {y3}', v=f'+{r:.1f}%', sub='ALL PRICES (CPI-U)', anim=True, red=True)),
             (f"Out of every three-year stretch since 1995, that ranks number {rank}.", dict(t='big', top='RANK SINCE 1995', v=f'#{rank}', sub=f'OF {len(allr)} PERIODS')),
             (f"The fastest was {allr[0][0]} to {allr[0][0] + 3}: {allr[0][1]:.1f} percent.", dict(t='big', top=f'{allr[0][0]} TO {allr[0][0] + 3}', v=f'+{allr[0][1]:.1f}%', sub='FASTEST SINCE 1995', red=True)),
             ("Which years hit you hardest? Comment below.", dict(t='big', top=f'{allr[0][0]} TO {allr[0][0] + 3}', v=f'+{allr[0][1]:.1f}%', sub='FASTEST SINCE 1995', red=True, cta='WHICH YEARS HURT?'))]
        title = f"Prices From {y0} to {y3}: How Fast Did They Rise?"
    beats = [b for b, _ in B]; scenes = [s for _, s in B]
    desc = title + '\n\n' + '\n'.join(beats[:-1]) + f'\n\n{src}\nNot financial advice.\n\n#thenvsnow #prices #inflation #nostalgia #shorts'
    return dict(fmt=kg, key=key, title=title[:95], desc=desc, beats=beats, scenes=scenes)


# ---------------------------------------------------------------- sahneler
def card(img, x, y, w, h, year, lines, total, now=False, prog=1.0):
    n = len(lines); lh, fs = (100, 52) if n <= 2 else (78, 46)
    tvn.receipt(img, x, y, w, h, prog, year, lines, total, now=now, lh=lh, fs=fs)


def chart(img, d, sc, t):
    it = sc['it']; ys = yrs(it); y1 = L(it)
    if sc.get('from_'): ys = [y for y in ys if y >= sc['from_']]
    val = (lambda y: adj(p(it, y), y, y1)) if sc.get('real') else (lambda y: p(it, y))
    x0, x1, yt, yb = 120, 980, 420, 1250
    hi = max(val(y) for y in ys) * 1.12; lo = 0
    d.rounded_rectangle([60, 300, 1020, 1380], radius=30, fill=PAPER)
    d.text((W // 2, 350), (SHORT[it] + ('  (TODAY $)' if sc.get('real') else '')), font=font(MONO, 40), fill=INK, anchor='mm')
    X = lambda y: x0 + (x1 - x0) * (y - ys[0]) / max(1, ys[-1] - ys[0]); Y = lambda v: yb - (yb - yt) * (v - lo) / (hi - lo)
    for g in range(5):
        gv = hi * g / 5; d.line([(x0, Y(gv)), (x1, Y(gv))], fill=(225, 218, 200), width=2)
        d.text((x0 - 10, Y(gv)), money(gv), font=font(MONO, 24), fill=FADED, anchor='rm')
    sel = ys if sc.get('n', 99) >= 99 else [y for y in ys if y in sc.get('ys', ys)][:sc['n']]
    k = ease(t / 1.6) if sc.get('anim') else 1.0
    sel = sel[:max(1, int(len(sel) * k))] if sel else []
    pts = [(X(y), Y(val(y))) for y in sel]
    if len(pts) > 1: d.line(pts, fill=RED, width=8, joint='curve')
    for (x, yy), y in zip(pts, sel):
        if sc.get('n', 99) < 99: d.ellipse([x - 10, yy - 10, x + 10, yy + 10], fill=RED); d.text((x, yy - 30), money(val(y)), font=font(MONO, 30), fill=INK, anchor='mb')
    if sc.get('double'):
        d.line([(x0, Y(sc['double'])), (x1, Y(sc['double']))], fill=GREEN, width=4); d.text((x1, Y(sc['double']) - 8), '2X', font=font(DISP, 44), fill=GREEN, anchor='rb')
    for mk, col in ((sc.get('mark'), RED), (sc.get('mark2'), GREEN)):
        if mk and mk in PRICES[it]['years'] and mk >= ys[0]:
            d.ellipse([X(mk) - 18, Y(val(mk)) - 18, X(mk) + 18, Y(val(mk)) + 18], outline=col, width=7)
            d.text((min(max(X(mk), 260), 820), Y(val(mk)) - 34), f'{mk}: {money(val(mk))}', font=font(MONO, 34), fill=col, anchor='mb')
    for y in (ys[0], ys[len(ys) // 2], ys[-1]):
        d.text((X(y), yb + 40), str(y), font=font(MONO, 30), fill=FADED, anchor='mm')


def pills(d, opts, r, y0=1420):
    n = len(opts); w = 900 // n
    for i, o in enumerate(opts):
        x = 90 + i * w; on = r == i
        d.rounded_rectangle([x + 8, y0, x + w - 8, y0 + 120], radius=60, fill=YEL if on else PAPER, outline=INK, width=4)
        d.text((x + w // 2, y0 + 60), o, font=font(DISP, 66 if len(o) < 9 else 46), fill=INK, anchor='mm')


def frame(base, v, bi, t):
    img = base.copy(); d = ImageDraw.Draw(img); sc = v['scenes'][bi]; T = sc['t']; a = ease(t / 0.7) if sc.get('anim') else 1.0
    if T == 'rec':
        lines = sc['lines']; h = 230 + (100 if len(lines) <= 2 else 78) * len(lines) + 110
        card(img, 90, 260, 900, h, sc['year'], lines, sum(x for _, x, _ in lines), prog=min(1.0, t / 1.2) if bi == 0 else 1.0)
        if sc.get('opts'): pills(d, sc['opts'], sc.get('r'))
        if sc.get('now'): d.text((W // 2, 1300), f"TODAY: {money(sc['now'])}", font=font(DISP, 96), fill=RED, anchor='mm')
    elif T == 'pair':
        n = len(sc['l0']); h = 230 + (100 if n <= 2 else 78) * n + 110
        card(img, 90, 230, 900, h, sc['y0'], sc['l0'], sum(x for _, x, _ in sc['l0']))
        card(img, 90, 260 + h, 900, h, sc['y1'], sc['l1'], sum(x for _, x, _ in sc['l1']), now=True, prog=min(1.0, t / 1.2) if not sc.get('cta') else 1.0)
    elif T == 'multi':
        cs = sc['cards']; n = len(cs); hh = min(330, 1250 // n)
        for i, c in enumerate(cs[:sc['n']]):
            card(img, 90, 220 + i * (hh + 20), 900, hh, c['y'], [(c['l'], c['v'], '$')], c['v'], now=(i == n - 1), prog=min(1.0, t / 1.0) if i == sc['n'] - 1 and bi > 0 else 1.0)
    elif T == 'chart':
        chart(img, d, sc, t)
    elif T == 'opts':
        d.text((W // 2, 520), sc['top'], font=font(DISP, 72 if len(sc['top']) < 28 else 52), fill=PAPER, anchor='mm')
        for i, o in enumerate(sc['o']):
            y = 700 + i * 200; on = sc.get('r') == i
            d.rounded_rectangle([120, y, 960, y + 150], radius=75, fill=YEL if on else PAPER, outline=INK, width=5)
            d.text((W // 2, y + 75), o, font=font(DISP, 80), fill=INK, anchor='mm')
    elif T == 'big':
        d.rounded_rectangle([90, 420, 990, 1250], radius=40, fill=PAPER)
        d.text((W // 2, 520), sc['top'], font=font(DISP, 76), fill=INK, anchor='mm')
        val = sc['v']; fs = 230 if len(val) <= 6 else 170 if len(val) <= 9 else 120
        d.text((W // 2, 830), val, font=font(DISP, int(fs * (0.6 + 0.4 * a))), fill=RED if sc.get('red') else INK, anchor='mm')
        d.text((W // 2, 1130), sc.get('sub', ''), font=font(MONO, 40), fill=FADED, anchor='mm')
    elif T == 'bars':
        d.text((W // 2, 300), sc['head'], font=font(DISP, 90), fill=PAPER, anchor='mm')
        for i, r in enumerate(sc['rows'][:sc['n']]):
            y = 420 + i * 200; ww = 800 * max(0.05, r['w']) * (ease(t / 0.8) if i == sc['n'] - 1 and not sc.get('cta') else 1.0)
            if 'r' in r: d.text((100, y + 40), f"#{r['r']}", font=font(DISP, 60), fill=YEL, anchor='lm')
            d.text((190, y + 40), r['l'], font=font(MONO, 42), fill=PAPER, anchor='lm')
            d.rectangle([190, y + 85, 190 + ww, y + 150], fill=r['c'])
            d.text((200 + ww + 10, y + 118), r['v'], font=font(DISP, 64), fill=r['c'], anchor='lm')
    elif T == 'tf':
        d.rounded_rectangle([90, 380, 990, 900], radius=40, fill=PAPER)
        for j, l in enumerate(tvn_wrap(d, sc['q'], font(MONO, 50), 820)[:5]):
            d.text((W // 2, 470 + j * 76), l, font=font(MONO, 50), fill=INK, anchor='mm')
        for i, o in enumerate(['TRUE', 'FALSE']):
            x = 110 + i * 440; on = sc.get('r') == i
            d.rounded_rectangle([x, 1000, x + 420, 1150], radius=75, fill=(GREEN if on else PAPER), outline=INK, width=5)
            d.text((x + 210, 1075), o, font=font(DISP, 90), fill=PAPER if on else INK, anchor='mm')
    if sc.get('cta'):
        d.rounded_rectangle([90, 1600, 990, 1740], radius=40, fill=YEL)
        d.text((W // 2, 1670), sc['cta'], font=font(DISP, 90 if len(sc['cta']) < 18 else 70), fill=INK, anchor='mm')
    return img


def tvn_wrap(d, text, f, maxw):
    out, cur = [], ''
    for w in text.split():
        t = (cur + ' ' + w).strip()
        if d.textlength(t, font=f) > maxw and cur: out.append(cur); cur = w
        else: cur = t
    return out + [cur] if cur else out


def render(v, mp4):
    tmp = mp4.with_suffix(''); tmp.mkdir(parents=True, exist_ok=True)
    auds, durs = [], []
    for i, b in enumerate(v['beats']):
        a = tmp / f'a{i}.mp3'
        try:
            tvn.tts(b, a)
        except Exception:
            import renderer
            a = tmp / f'a{i}.wav'; renderer.piper_tts(b, a)
        w = tmp / f'w{i}.wav'
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(a), '-af', 'silenceremove=start_periods=1:start_threshold=-45dB,areverse,'
                        'silenceremove=start_periods=1:start_threshold=-45dB,areverse,apad=pad_dur=0.3' + (',apad=whole_dur=2.2' if b in ('Pick one.', 'Think about it.', 'Watch the line.') else ''),
                        '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le', str(w)], check=True)
        auds.append(w); durs.append(tvn.dur(w))
    lst = tmp / 'a.txt'; lst.write_text(''.join(f"file '{a}'\n" for a in auds))
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(lst), '-ar', '44100', '-ac', '2', str(tmp / 'voice.wav')], check=True)
    base = tvn.background()
    p_ = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                           '-i', str(tmp / 'voice.wav'), '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p',
                           '-c:a', 'aac', '-b:a', '160k', '-shortest', '-movflags', '+faststart', str(mp4)], stdin=subprocess.PIPE)
    for i, dd in enumerate(durs):
        last = None
        for k in range(int(dd * FPS)):
            t = k / FPS
            if t > 1.8 and last is not None: p_.stdin.write(last); continue
            fr = frame(base, v, i, t).tobytes()
            if t > 1.75: last = fr
            p_.stdin.write(fr)
    p_.stdin.close(); p_.wait()
    if p_.returncode: raise RuntimeError('ffmpeg hata')
    return mp4
