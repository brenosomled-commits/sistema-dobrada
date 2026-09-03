import pathlib
p=pathlib.Path(r'C:\SistemaOS\templates\editar_venda.html')
t=p.read_text(encoding='utf-8')
# fix wrapper
t=t.replace("function viaHTMLWrapper(isSegunda){","function _viaWrapper(isSegunda){")
t=t.replace("v1.innerHTML=viaHTML(false)","v1.innerHTML=viaHTML()")
t=t.replace("v2.innerHTML=viaHTML(true)","v2.innerHTML=viaHTML()")
# ensure signature is handled outside
if "viaHTMLWrapper" in t:
    t=t.replace("viaHTMLWrapper","viaHTML")
p.write_text(t, encoding='utf-8')
print("fixed")
