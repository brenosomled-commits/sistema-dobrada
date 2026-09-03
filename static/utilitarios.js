/* ============================================
   SISTEMA SOMLED - UTILITARIOS COMPARTILHADOS
   ============================================ */

(function (window) {
    'use strict';

    // ===================== TOAST =====================

    function toast(tipo, mensagem, duracao = 4000) {
        const container = document.querySelector('.toast-container');
        const icones = {
            sucesso: '✓',
            erro: '✕',
            aviso: '!',
            info: 'ℹ'
        };

        const toastEl = document.createElement('div');
        toastEl.className = 'toast toast-' + (tipo || 'info');
        toastEl.innerHTML =
            '<span class="toast-icon">' + (icones[tipo] || 'ℹ') + '</span>' +
            '<span class="toast-mensagem"></span>' +
            '<button class="toast-fechar" onclick="this.parentElement.remove()">×</button>';

        toastEl.querySelector('.toast-mensagem').textContent = mensagem;

        let existente = document.querySelector('.toast-container');
        if (!existente) {
            existente = document.createElement('div');
            existente.className = 'toast-container';
            document.body.appendChild(existente);
        }

        existente.appendChild(toastEl);

        const fechar = function () {
            toastEl.classList.add('toast-saindo');
            setTimeout(function () {
                toastEl.remove();
            }, 300);
        };

        if (duracao > 0) {
            setTimeout(fechar, duracao);
        }

        return toastEl;
    }

    const Toast = {
        sucesso: function (msg, tempo) { toast('sucesso', msg, tempo); },
        erro: function (msg, tempo) { toast('erro', msg, tempo); },
        aviso: function (msg, tempo) { toast('aviso', msg, tempo); },
        info: function (msg, tempo) { toast('info', msg, tempo); }
    };

    // ===================== MASCARA / FORMATAÇÃO =====================

    function formatarMoeda(valor) {
        return Number(valor || 0).toLocaleString('pt-BR', {
            style: 'currency',
            currency: 'BRL'
        });
    }

    function formatarNumero(valor) {
        return Number(valor || 0).toFixed(2).replace('.', ',');
    }

    function formatarDataBrasil(data) {
        if (!data) return '';
        const partes = String(data).split('-');
        if (partes.length !== 3) return data;
        return partes[2] + '/' + partes[1] + '/' + partes[0];
    }

    function dataHoje() {
        const hoje = new Date();
        const ano = hoje.getFullYear();
        const mes = String(hoje.getMonth() + 1).padStart(2, '0');
        const dia = String(hoje.getDate()).padStart(2, '0');
        return ano + '-' + mes + '-' + dia;
    }

    function dataHojeBrasil() {
        const hoje = new Date();
        return hoje.toLocaleDateString('pt-BR');
    }

    // Mascara de telefone: (XX) XXXXX-XXXX
    function mascaraTelefone(input) {
        let valor = input.value.replace(/\D/g, '');
        if (valor.length > 11) valor = valor.slice(0, 11);

        if (valor.length > 10) {
            valor = valor.replace(/^(\d{2})(\d{5})(\d{4})$/, '($1) $2-$3');
        } else if (valor.length > 6) {
            valor = valor.replace(/^(\d{2})(\d{4})(\d{0,4})$/, '($1) $2-$3');
        } else if (valor.length > 2) {
            valor = valor.replace(/^(\d{2})(\d{0,5})$/, '($1) $2');
        } else if (valor.length > 0) {
            valor = valor.replace(/^(\d{0,2})$/, '($1');
        }

        input.value = valor;
    }

    function adicionarMascaraTelefone(seletor) {
        document.querySelectorAll(seletor).forEach(function (el) {
            if (!el.dataset.mascaraTelefone) {
                el.dataset.mascaraTelefone = '1';
                el.addEventListener('input', function () { mascaraTelefone(el); });
            }
        });
    }

    // ===================== LOADING =====================

    function mostrarLoading(texto) {
        const overlay = document.createElement('div');
        overlay.className = 'loading-overlay';
        overlay.id = 'loading-overlay';
        overlay.innerHTML =
            '<div class="loading-box">' +
            '<div class="spinner"></div>' +
            '<div class="loading-label">' + (texto || 'Carregando…') + '</div>' +
            '</div>';
        document.body.appendChild(overlay);
    }

    function esconderLoading() {
        const overlay = document.getElementById('loading-overlay');
        if (overlay) overlay.remove();
    }

    // ===================== MODAL DE CONFIRMAÇÃO =====================

    function confirmacao(opcoes) {
        return new Promise(function (resolve) {
            const overlay = document.createElement('div');
            overlay.className = 'modal-overlay';

            const modal = document.createElement('div');
            modal.className = 'modal';

            const titulo = opcoes.titulo || 'Confirmar ação';
            const mensagem = opcoes.mensagem || 'Tem certeza?';
            const textoSim = opcoes.textoSim || 'Confirmar';
            const textoNao = opcoes.textoNao || 'Cancelar';
            const tipo = opcoes.tipo || 'danger';

            const classeBotao = tipo === 'danger' ? 'btn-danger' :
                                tipo === 'warning' ? 'btn-warning' : 'btn-primary';

            modal.innerHTML =
                '<div class="modal-header"><h3>' + titulo + '</h3></div>' +
                '<div class="modal-body"><p>' + mensagem + '</p></div>' +
                '<div class="modal-footer">' +
                '<button class="btn btn-outline" data-acao="nao">' + textoNao + '</button>' +
                '<button class="btn ' + classeBotao + '" data-acao="sim">' + textoSim + '</button>' +
                '</div>';

            overlay.appendChild(modal);
            document.body.appendChild(overlay);

            function fechar(resultado) {
                overlay.remove();
                resolve(resultado);
            }

            overlay.addEventListener('click', function (e) {
                if (e.target === overlay) fechar(false);
            });

            modal.querySelector('[data-acao="sim"]').addEventListener('click', function () { fechar(true); });
            modal.querySelector('[data-acao="nao"]').addEventListener('click', function () { fechar(false); });
        });
    }

    function alerta(mensagem, titulo) {
        return confirmacao({
            titulo: titulo || 'Aviso',
            mensagem: mensagem,
            textoSim: 'OK',
            textoNao: '',
            tipo: 'primary'
        });
    }
    // Nota: alerta() não é usado diretamente; usar Toast.

    // ===================== NAVEGAÇÃO (MENU LATERAL) =====================

    function initSidebar() {
        const toggle = document.querySelector('.mobile-toggle');
        const sidebar = document.querySelector('.sidebar');

        if (!toggle || !sidebar) return;

        const overlay = document.createElement('div');
        overlay.className = 'sidebar-overlay';
        document.body.appendChild(overlay);

        toggle.addEventListener('click', function () {
            sidebar.classList.toggle('aberta');
            overlay.style.display = sidebar.classList.contains('aberta') ? 'block' : 'none';
        });

        overlay.addEventListener('click', function () {
            sidebar.classList.remove('aberta');
            overlay.style.display = 'none';
        });

        sidebar.querySelectorAll('.sidebar-link').forEach(function (link) {
            link.addEventListener('click', function () {
                if (window.innerWidth <= 1024) {
                    sidebar.classList.remove('aberta');
                    overlay.style.display = 'none';
                }
            });
        });

        // Marca link ativo baseado na URL
        const caminho = window.location.pathname;
        sidebar.querySelectorAll('.sidebar-link').forEach(function (link) {
            let destino = link.getAttribute('data-rota') || link.getAttribute('href') || '';
            if (destino && destino !== '#' && caminho === destino) {
                link.classList.add('ativa');
            }
        });
    }

    // ===================== NOTIFICAÇÃO GLOBAL DE ENTREGAS (todas as máquinas + PWA) =====================

    (function(){
        if(window.location.pathname==="/entregas") return;
        let primeiro=true;
        let ultimoIds=new Set(JSON.parse(localStorage.getItem("entregas_ids")||"[]"));
        let audioCtx=null;
        function beepGlobal(){
            try{
                if(!audioCtx) audioCtx=new (window.AudioContext||window.webkitAudioContext)();
                if(audioCtx.state==="suspended") audioCtx.resume();
                const beep=(f,d,dl)=>{
                    const o=audioCtx.createOscillator(), g=audioCtx.createGain();
                    o.type="sine"; o.frequency.value=f; o.connect(g); g.connect(audioCtx.destination);
                    g.gain.setValueAtTime(0.85,audioCtx.currentTime+dl);
                    g.gain.exponentialRampToValueAtTime(0.01,audioCtx.currentTime+dl+d);
                    o.start(audioCtx.currentTime+dl); o.stop(audioCtx.currentTime+dl+d);
                };
                beep(880,0.18,0); beep(1200,0.18,0.2); beep(880,0.35,0.4);
                if("vibrate" in navigator) navigator.vibrate([180,80,180]);
            }catch(e){}
            try{
                const txt="Nova entrega"; 
                if("speechSynthesis" in window){ const u=new SpeechSynthesisUtterance(txt); u.lang="pt-BR"; u.rate=1; speechSynthesis.cancel(); speechSynthesis.speak(u); }
            }catch(e){}
            try{ if("Notification" in window && Notification.permission==="granted"){ new Notification("🚚 Nova entrega",{body:"Nova entrega registrada — verifique em Entregas"}); } }catch(e){}
        }
        if("Notification" in window && Notification.permission==="default"){ try{ Notification.requestPermission(); }catch(e){} }
        document.addEventListener("click", function prim(){ if(!audioCtx) try{ audioCtx=new (window.AudioContext||window.webkitAudioContext)(); }catch(e){} document.removeEventListener("click", prim); }, {once:true});
        async function verificar(){
            try{
                const r=await fetch("/api/entregas",{credentials:"same-origin"});
                if(!r.ok) return;
                const ct=r.headers.get("content-type")||"";
                if(!ct.includes("application/json")) return;
                const lista=await r.json();
                if(!Array.isArray(lista)) return;
                const ids=new Set(lista.map(e=>e.id));
                if(primeiro){ ultimoIds=ids; localStorage.setItem("entregas_ids", JSON.stringify([...ids])); primeiro=false; return; }
                const novas=lista.filter(e=>!ultimoIds.has(e.id));
                if(novas.length>0){
                    beepGlobal();
                    const msg=novas.length===1 ? "🚚 Nova entrega: "+(novas[0].cliente||"ENT"+String(novas[0].numero).padStart(4,"0")) : "🚚 "+novas.length+" novas entregas";
                    Toast.info(msg, 6000);
                }
                ultimoIds=ids;
                localStorage.setItem("entregas_ids", JSON.stringify([...ids]));
            }catch(e){}
        }
        setTimeout(verificar, 4000);
        setInterval(verificar, 15000);
        window.addEventListener("storage", function(e){ if(e.key==="entregas_ids") try{ ultimoIds=new Set(JSON.parse(e.newValue||"[]")); }catch(_){} });
    })();

    // ===================== IMPRESSÃO CENTRALIZADA =====================

    function _areaImpressaoGlobal() {
        let area = document.getElementById("areaImpressaoGlobal");
        if (!area) {
            area = document.createElement("div");
            area.id = "areaImpressaoGlobal";
            area.style.display = "none";
            document.body.appendChild(area);
        }
        return area;
    }

    function _imprimirDocumento(html) {
        const area = _areaImpressaoGlobal();
        area.innerHTML = html;
        area.style.display = "block";
        window.print();
        setTimeout(function () { area.style.display = "none"; area.innerHTML = ""; }, 500);
    }

    function _f2(n) { return Number(n || 0).toFixed(2).replace(".", ","); }
    function _fmtDMA(d) { if (!d) return ""; const s = String(d).split(" ")[0]; const p = s.split("-"); return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : String(d); }
    function _condTxt(c) { return c === 'aprazo' ? 'A PRAZO' : (({dinheiro: 'DINHEIRO', cartadebito: 'CARTAO DEBITO', cartocredito: 'CARTAO CREDITO', pix: 'PIX SICOOB', sicoob: 'PIX SICOOB', pixinter: 'PIX INTER', pixmaq: 'PIX MAQUINA', avista: 'A VISTA'}[String(c)]) || (String(c) || '-').toUpperCase()); }
    function _esc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
    function _fmtNumDoc(c, n) {
        if (String(c || "").toUpperCase() === "OS") return "OS" + String(n || 0).padStart(5, "0");
        return "SL" + String(n || 0).padStart(4, "0");
    }

    /* ===================== ORDEM DE SERVIÇO (modelo único oficial) ===================== */
    function imprimirOS(dados) {
        const d = dados || {};
        const cliente = _esc(d.cliente) || "CONSUMIDOR FINAL";
        const telefone = _esc(d.telefone);
        const responsavel = _esc(d.responsavel) || "-";
        const numero = "Nº " + String(d.numero || "").padStart(5, "0");
        const data = _fmtDMA(d.data_entrada || d.data) || "-";
        const problema = _esc(d.problema) || "-";
        const solucao = _esc(d.solucao) || "-";
        const maoObra = Number(d.mao_obra || 0);
        const total = Number(d.total || 0);
        const itens = Array.isArray(d.itens) ? d.itens : [];
        const status = _esc(d.status) || "";

        let linhasItens = "";
        itens.forEach(function (it) {
            const nome = _esc(it.nome != null ? it.nome : it.descricao);
            const qtd = it.quantidade != null ? it.quantidade : "";
            const valor = Number(it.valor || 0);
            const sub = Number(qtd || 0) * valor;
            linhasItens +=
                '<div class="osdoc-item"><span class="osdoc-item-qtd">' + (qtd || "") + '</span>' +
                '<span class="osdoc-item-nome">' + (nome || "-") + '</span>' +
                '<span class="osdoc-item-valor">R$ ' + _f2(valor) + '</span>' +
                '<span class="osdoc-item-total">R$ ' + _f2(sub) + '</span></div>';
        });
        if (!linhasItens) {
            linhasItens = '<div class="osdoc-item"><span class="osdoc-item-nome">Nenhum item</span><span></span><span></span></div>';
        }

        const html =
            '<div class="osdoc">' +
                '<div class="osdoc-topo">' +
                    '<div class="osdoc-logo">SOMLED<div class="osdoc-logo-sub">SOLUÇÕES EM ILUMINAÇÃO</div></div>' +
                    '<div class="osdoc-titulo">ORDEM DE SERVIÇO</div>' +
                    '<div class="osdoc-numero">' + numero + '</div>' +
                '</div>' +
                (status ? '<div class="osdoc-status">' + status.toUpperCase() + '</div>' : '') +
                '<div class="osdoc-grid">' +
                    '<div class="osdoc-campo osdoc-campo-largo"><span class="osdoc-rotulo">CLIENTE</span><div class="osdoc-valor">' + cliente + (telefone ? ' <span class="osdoc-tel">· ' + telefone + '</span>' : '') + '</div></div>' +
                    '<div class="osdoc-campo"><span class="osdoc-rotulo">TELEFONE</span><div class="osdoc-valor">' + (telefone || "-") + '</div></div>' +
                    '<div class="osdoc-campo"><span class="osdoc-rotulo">DATA ENTRADA</span><div class="osdoc-valor">' + data + '</div></div>' +
                    '<div class="osdoc-campo"><span class="osdoc-rotulo">RESPONSÁVEL</span><div class="osdoc-valor">' + responsavel + '</div></div>' +
                '</div>' +
                '<div class="osdoc-secao"><div class="osdoc-secao-titulo">PROBLEMA RELATADO</div><div class="osdoc-caixa">' + problema + '</div></div>' +
                '<div class="osdoc-secao"><div class="osdoc-secao-titulo">SOLUÇÃO / SERVIÇO EXECUTADO</div><div class="osdoc-caixa">' + solucao + '</div></div>' +
                '<div class="osdoc-secao"><div class="osdoc-secao-titulo">ITENS UTILIZADOS</div>' +
                    '<div class="osdoc-itens-cab">' +
                        '<span class="osdoc-item-qtd">QTD.</span><span class="osdoc-item-nome">ITEM</span><span class="osdoc-item-valor">VALOR UNIT.</span><span class="osdoc-item-total">TOTAL</span>' +
                    '</div>' + linhasItens +
                '</div>' +
                '<div class="osdoc-totais">' +
                    '<div class="osdoc-total-linha"><span>MÃO DE OBRA</span><span>R$ ' + _f2(maoObra) + '</span></div>' +
                    '<div class="osdoc-total-final"><span>TOTAL</span><span>R$ ' + _f2(total) + '</span></div>' +
                '</div>' +
                '<div class="osdoc-assinaturas">' +
                    '<div class="osdoc-assinatura"><div class="osdoc-assinatura-linha"></div><div class="osdoc-assinatura-rotulo">ASSINATURA DO RESPONSÁVEL</div></div>' +
                    '<div class="osdoc-assinatura"><div class="osdoc-assinatura-linha"></div><div class="osdoc-assinatura-rotulo">ASSINATURA DO CLIENTE</div></div>' +
                '</div>' +
                '<div class="osdoc-rodape">DOCUMENTO SEM VALOR FISCAL — SISTEMA DE CONTROLE INTERNO SOMLED — NÃO SUBSTITUI NOTA FISCAL ELETRÔNICA</div>' +
            '</div>';
        _imprimirDocumento(html);
    }

    /* ===================== NOTA DOBRADA (modelo único oficial) ===================== */
    function imprimirNotaDobrada(v) {
        const dados = v || {};
        const itens = Array.isArray(dados.itens) ? dados.itens : [];
        const cliente = _esc(dados.cliente) || "CONSUMIDOR FINAL";
        const telefone = _esc(dados.telefone);
        const vendedor = _esc(dados.vendedor) || "-";
        const obs = _esc(dados.observacao) || "-";
        const data = _fmtDMA(dados.data) || "-";
        const venc = _fmtDMA(dados.vencimento);
        const condTxt = _condTxt(dados.condicao);
        const descontoPct = Number(dados.desconto != null ? dados.desconto : 0);
        const totalFinal = Number(dados.total || 0);
        const totalItens = descontoPct > 0 ? (totalFinal / (1 - descontoPct / 100)) : totalFinal;
        const vDesc = totalItens * descontoPct / 100;
        const venda = _fmtNumDoc("VENDA", dados.numero);

        let linhas = "";
        itens.forEach(function (it) {
            const q = it.quantidade != null ? it.quantidade : "";
            const nome = _esc(it.descricao != null ? it.descricao : it.nome);
            const valor = Number(it.valor || 0);
            const sub = Number(q || 0) * valor;
            linhas +=
                '<div class="nota-item-impressao"><span>' + q + '</span><span style="padding-right:4px">' + nome + '</span>' +
                '<span>R$ ' + _f2(valor) + '</span><span>R$ ' + _f2(sub) + '</span></div>';
        });

        function viaHTML(isSegunda) {
            return '<div class="via-impressao">' +
                '<div class="via-etiqueta"><span>' + (isSegunda ? 'VIA DA LOJA — 2ª VIA' : 'VIA DO CLIENTE — 1ª VIA') + '</span><span>' + (isSegunda ? 'CONTROLE INTERNO' : '') + '</span></div>' +
                '<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;padding:2px 0 5px;border-bottom:1.2px solid #000">' +
                    '<div style="flex:1"></div>' +
                    '<div style="text-align:center;flex:1"><div style="font-weight:900;font-size:16pt;letter-spacing:.02em;line-height:1">SOMLED</div><div style="font-size:6pt;letter-spacing:.14em;margin-top:1px">SOLUÇÕES EM ILUMINAÇÃO</div></div>' +
                    '<div style="flex:1;display:flex;justify-content:flex-end"><div style="border:1.2px solid #000;padding:3px 8px;text-align:center;min-width:28mm"><div style="font-size:6.5pt;font-weight:700;letter-spacing:.06em;line-height:1.1">NOTA DE ORÇAMENTO<br>SEM VALOR FISCAL</div><div style="font-size:12pt;font-weight:900;margin-top:2px">' + venda + '</div></div></div>' +
                '</div>' +
                '<div style="display:grid;grid-template-columns:1fr 1fr;gap:2px 12px;margin-top:5px;font-size:8.5pt;line-height:1.35">' +
                    '<div><span style="font-size:7pt;font-weight:700">CLIENTE:</span> <span style="font-weight:600">' + cliente + '</span>' + (telefone ? ' <span style="font-size:7pt;font-weight:600">· TEL: ' + telefone + '</span>' : '') + '</div>' +
                    '<div><span style="font-size:7pt;font-weight:700">CONDIÇÃO:</span> <span style="border:1px solid #000;padding:1px 5px;font-size:7pt;font-weight:700">' + condTxt + '</span></div>' +
                    '<div><span style="font-size:7pt;font-weight:700">VENDA:</span> <span style="font-weight:800">' + venda + '</span></div>' +
                    '<div><span style="font-size:7pt;font-weight:700">DATA:</span> ' + data + '</div>' +
                    '<div><span style="font-size:7pt;font-weight:700">VENDEDOR:</span> ' + vendedor + '</div>' +
                    '<div><span style="font-size:7pt;font-weight:700">OBSERVAÇÃO:</span> ' + obs + '</div>' +
                    '<div><span style="font-size:7pt;font-weight:700">VENCIMENTO:</span> ' + (venc || (dados.condicao === 'aprazo' ? '30 DIAS' : '-')) + '</div>' +
                '</div>' +
                '<div style="border-top:1px solid #000;margin:5px 0 0"></div>' +
                '<div class="nota-tabela-cabecalho"><span>QTD.</span><span>DESCRIÇÃO</span><span>VALOR UNIT.</span><span>SUBTOTAL</span></div>' +
                linhas +
                '<div style="display:flex;gap:12px;align-items:flex-end;margin-top:6px;flex:1">' +
                    '<div style="flex:1;text-align:center;padding-top:8px"><div class="via-assinatura-linha" style="width:68mm"></div><div class="via-assinatura-rotulo">' + (isSegunda ? 'ASSINATURA — VIA DA LOJA' : 'ASSINATURA DO CLIENTE') + '</div>' + (!isSegunda ? '<div style="font-size:6pt;color:#374151;margin-top:2px">Ao assinar, declaro que estou ciente<br>das condições deste orçamento.</div>' : '') + '</div>' +
                    '<div style="width:86mm;border:1px solid #000;padding:4px 6px;font-size:8pt;line-height:1.35">' +
                        '<div style="display:flex;justify-content:space-between"><span style="font-weight:700">TOTAL:</span><span>R$ ' + _f2(totalItens) + '</span></div>' +
                        '<div style="display:flex;justify-content:space-between"><span style="font-weight:700">DESCONTO:</span><span>' + descontoPct + '%</span></div>' +
                        '<div style="display:flex;justify-content:space-between"><span style="font-weight:700">VALOR DESCONTO:</span><span>R$ ' + _f2(vDesc) + '</span></div>' +
                        '<div style="display:flex;justify-content:space-between;border-top:1px solid #000;padding-top:3px;margin-top:3px"><span style="font-weight:800">TOTAL FINAL:</span><span style="font-weight:800">R$ ' + _f2(totalFinal) + '</span></div>' +
                    '</div>' +
                '</div>' +
                '<div class="via-rodape">CUPOM NÃO FISCAL — DOCUMENTO SEM VALOR FISCAL — APENAS ORÇAMENTO</div>' +
            '</div>';
        }

        const html = '<div class="pagina-impressao">' + viaHTML(false) +
            '<div class="recorte-linha"><span style="display:flex;align-items:center;gap:5px;font-size:7.5px;font-weight:800;color:#111827;letter-spacing:.07em;text-transform:uppercase;white-space:nowrap"><span style="font-size:11px">✂</span> RECORTE AQUI <span style="font-weight:600;opacity:.6">|</span> VIA DO CLIENTE ↕ VIA DA LOJA</span></div>' +
            viaHTML(true) + '</div>';
        _imprimirDocumento(html);
    }

    function imprimirEntrega(e) {
        const d = e || {};
        const itens = Array.isArray(d.itens) ? d.itens : [];
        const html = '<div style="width:76mm;margin:0 auto;font-size:11px;line-height:1.5;color:#000">' +
            '<div style="text-align:center;font-weight:900;font-size:15px">SOMLED</div>' +
            '<div style="text-align:center;font-size:9px">SOLUÇÕES EM ILUMINAÇÃO</div>' +
            '<div style="text-align:center;font-weight:800;border-top:1px solid #000;border-bottom:1px solid #000;padding:2px 0;margin:5px 0">ENTREGA ENT' + String(d.numero || "").padStart(4, "0") + '</div>' +
            '<div><b>CLIENTE:</b> ' + _esc(d.cliente) + (d.telefone ? ' · ' + _esc(d.telefone) : '') + '</div>' +
            '<div><b>ENDEREÇO:</b> ' + _esc(d.endereco) + (d.bairro ? ' · ' + _esc(d.bairro) : '') + '</div>' +
            '<div><b>ENTREGADOR:</b> ' + _esc(d.entregador) + ' · <b>TAXA:</b> R$ ' + _f2(d.taxa) + '</div>' +
            '<div><b>DATA:</b> ' + _fmtDMA(d.data_entrega) + (d.horario ? ' ' + _esc(d.horario) : '') + ' · <b>STATUS:</b> ' + _esc(d.status) + '</div>' +
            '<div><b>OBS:</b> ' + _esc(d.observacao) + '</div>' +
            '<div style="margin-top:10px;border-top:1px solid #000;text-align:center;padding-top:3px"><b>ASSINATURA DO CLIENTE</b></div>' +
            '<div style="margin-top:6px;text-align:center;font-size:8px">SEM VALOR FISCAL — CONTROLE INTERNO</div>' +
        '</div>';
        _imprimirDocumento(html);
    }

    function solicitarAprovacao(acao, referencia, detalhe){
        return new Promise(function(resolver){
            var fundo=document.createElement('div');
            fundo.style.cssText='position:fixed;inset:0;background:rgba(15,23,42,.55);z-index:99999;display:flex;align-items:center;justify-content:center;padding:16px;';
            var card=document.createElement('div');
            card.style.cssText='background:#fff;color:#111;border-radius:16px;padding:22px;max-width:400px;width:100%;box-shadow:0 20px 45px rgba(0,0,0,.35);font-family:inherit;';
            card.innerHTML=
                '<div style="font-size:1.15rem;font-weight:800;margin-bottom:4px">🔒 APROVAÇÃO DO GERENTE NECESSÁRIA</div>'+
                '<div style="font-size:.85rem;color:#6b7280;margin-bottom:14px">Ação: <b>'+_esc(acao)+'</b>'+(referencia?' — <b>'+_esc(referencia)+'</b>':'')+'</div>'+
                (detalhe&&String(detalhe)!==acao?'<div style="font-size:.8rem;color:#374151;background:#f3f4f6;border-radius:8px;padding:8px 10px;margin-bottom:12px">'+_esc(String(detalhe))+'</div>':'')+
                '<div style="margin-bottom:10px"><label style="display:block;font-size:.75rem;font-weight:700;color:#374151;margin-bottom:4px">LOGIN DO GERENTE</label><input type="text" id="aprovLogin" autocomplete="off" style="width:100%;padding:10px;border:1px solid #d1d5db;border-radius:8px;font-size:.95rem"></div>'+
                '<div style="margin-bottom:16px"><label style="display:block;font-size:.75rem;font-weight:700;color:#374151;margin-bottom:4px">SENHA DO GERENTE</label><input type="password" id="aprovSenha" autocomplete="off" style="width:100%;padding:10px;border:1px solid #d1d5db;border-radius:8px;font-size:.95rem"></div>'+
                '<div style="display:flex;gap:10px"><button id="aprovCancelar" type="button" style="flex:1;padding:11px;border-radius:10px;border:1px solid #d1d5db;background:#fff;color:#111;font-weight:700;cursor:pointer">Cancelar</button><button id="aprovConfirmar" type="button" style="flex:1;padding:11px;border-radius:10px;border:0;background:#1a56db;color:#fff;font-weight:800;cursor:pointer">Aprovar</button></div>';
            fundo.appendChild(card);
            document.body.appendChild(fundo);
            var login=card.querySelector('#aprovLogin'), senha=card.querySelector('#aprovSenha');
            var ok=card.querySelector('#aprovConfirmar'), cx=card.querySelector('#aprovCancelar');
            function fechar(){ if(fundo.parentNode) fundo.parentNode.removeChild(fundo); }
            function confirmar(){
                ok.disabled=true; ok.textContent='Validando...';
                fetch('/api/aprovacoes', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ acao:acao, referencia:referencia||'', detalhe:detalhe||'', gerente_login:login.value.trim().toUpperCase(), gerente_senha:senha.value }) })
                .then(function(r){ return r.json().then(function(j){ return {ok:r.ok, j:j}; }); })
                .then(function(res){
                    if(res.ok && res.j.ok){ fechar(); resolver(true); }
                    else { ok.disabled=false; ok.textContent='Aprovar'; alert(res.j.erro||'Não foi possível aprovar'); }
                })
                .catch(function(){ ok.disabled=false; ok.textContent='Aprovar'; alert('Erro de conexão ao validar'); });
            }
            ok.addEventListener('click', confirmar);
            cx.addEventListener('click', function(){ fechar(); resolver(false); });
            senha.addEventListener('keydown', function(e){ if(e.key==='Enter'){ e.preventDefault(); confirmar(); } });
            login.focus();
        });
    }

    // ===================== EXPORTAÇÕES =====================

    window.SistemaUtil = {
        Toast: Toast,
        formatarMoeda: formatarMoeda,
        formatarNumero: formatarNumero,
        formatarDataBrasil: formatarDataBrasil,
        dataHoje: dataHoje,
        dataHojeBrasil: dataHojeBrasil,
        mascaraTelefone: mascaraTelefone,
        adicionarMascaraTelefone: adicionarMascaraTelefone,
        mostrarLoading: mostrarLoading,
        esconderLoading: esconderLoading,
        confirmacao: confirmacao,
        initSidebar: initSidebar,
        imprimirOS: imprimirOS,
        imprimirNotaDobrada: imprimirNotaDobrada,
        imprimirEntrega: imprimirEntrega,
        solicitarAprovacao: solicitarAprovacao
    };

})(window);
