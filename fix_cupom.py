import pathlib
for p in pathlib.Path(r'C:\SistemaOS\templates').glob('*.html'):
    t=p.read_text(encoding='utf-8')
    changed=False
    if 'NOTA ${fmtVenda' in t and 'SEM VALOR FISCAL' not in t[t.find('NOTA ${fmtVenda')-50:t.find('NOTA ${fmtVenda')+80]:
        # only for those specific headers that are just NOTA
        t=t.replace('NOTA ${fmtVenda', 'NOTA DE ORÇAMENTO SEM VALOR FISCAL ${fmtVenda')
        changed=True
    # Add footer cupom não fiscal to all via print templates where TOTAL FINAL exists
    if 'TOTAL FINAL' in t and 'SEM VALOR FISCAL' not in t.split('TOTAL FINAL')[-1][:500] and 'CUPOM' not in t:
        # Add footer after TOTAL FINAL div but before closing via
        # Find the via closing: look for TOTAL FINAL div line and add after
        marker = '<b>TOTAL FINAL:</b>'
        if marker in t:
            # Add footer after the total final's parent div
            # Insert after the total final line's closing </div></div>
            t=t.replace(
                '<b>TOTAL FINAL:</b><b>R$ ${Number(v.total).toFixed(2).replace',
                '<b>TOTAL FINAL:</b><b>R$ ${Number(v.total).toFixed(2).replace'
            )
            # Add footer injection point: after the via's total final, add a small footer
            # We'll inject a footer HTML after the total final's container
            # Find pattern for via footer
            if 'CUPOM NÃO FISCAL' not in t:
                t=t.replace(
                    '</div></div></div>`;',
                    '</div></div><div style="margin-top:10px;text-align:center;font-size:8px;color:#6b7280;border-top:1px dashed #9ca3af;padding-top:6px;letter-spacing:.06em">CUPOM NÃO FISCAL — SEM VALOR FISCAL — APENAS ORÇAMENTO</div></div>`;'
                )
                changed=True
    if changed:
        p.write_text(t, encoding='utf-8')
        print(f'updated {p.name}')
print('done')
