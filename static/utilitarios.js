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
            '<div class="flex flex-col items-center gap-3">' +
            '<div class="spinner"></div>' +
            (texto ? '<div style="color:var(--cor-texto-secundario)">' + texto + '</div>' : '') +
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
        initSidebar: initSidebar
    };

})(window);
