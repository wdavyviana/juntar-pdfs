"""
Juntar PDFs — aplicativo desktop para unir vários PDFs em um só e,
opcionalmente, comprimir o resultado (ou comprimir um único PDF).
Sem limites de quantidade, tamanho ou uso. Tudo roda localmente.

Requisitos:
    pip install PySide6 pymupdf pillow

Executar:
    python juntar_pdfs.py
"""

import multiprocessing
import os
import queue
import sys
from concurrent.futures import ProcessPoolExecutor

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def formatar_tamanho(num_bytes: int) -> str:
    for unidade in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.0f} {unidade}" if unidade == "B" else f"{num_bytes:.1f} {unidade}"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


# Níveis de compressão: (rótulo, DPI acima do qual a imagem é reduzida,
# DPI de destino, qualidade JPEG). Só as imagens são recomprimidas; texto
# e vetores continuam nítidos em qualquer nível.
NIVEIS_COMPRESSAO = [
    ("Leve — qualidade máxima", 220, 200, 80),
    ("Recomendada — equilíbrio", 170, 150, 65),
    ("Forte — menor arquivo", 110, 100, 50),
]
NIVEL_PADRAO = 1


def recomprimir_imagens(doc, dpi_limite: int, dpi_alvo: int, qualidade: int) -> None:
    """Reduz a resolução e recomprime as imagens de um PDF já aberto (PyMuPDF).

    Cada imagem é tratada uma única vez, mesmo que apareça em várias páginas
    (ex.: logo no cabeçalho), e só é trocada se o resultado ficar menor.
    Preserva preto e branco puro, imagens com transparência e imagens pequenas.
    """
    import io
    import math

    import pymupdf
    from PIL import Image

    # 1) Para cada imagem, a MENOR resolução em que ela aparece impressa
    #    (o maior tamanho na página) — é essa que precisa ser preservada.
    menor_dpi: dict[int, float] = {}
    info: dict[int, tuple] = {}
    for pagina in doc:
        for img in pagina.get_images(full=True):
            xref, smask, largura, altura, bpc = img[0], img[1], img[2], img[3], img[4]
            info[xref] = (smask, largura, altura, bpc)
            for ret in pagina.get_image_rects(xref):
                area_pol2 = (ret.width / 72) * (ret.height / 72)
                if area_pol2 <= 0:
                    continue
                dpi = math.sqrt(largura * altura / area_pol2)  # funciona até girada
                menor_dpi[xref] = min(menor_dpi.get(xref, dpi), dpi)

    # 2) Recomprime cada imagem uma única vez.
    for xref, dpi in menor_dpi.items():
        smask, largura, altura, bpc = info[xref]
        # Mantém: transparência (logos recortados), preto e branco puro
        # (já vem com compressão ótima) e imagens pequenas.
        if smask or bpc == 1 or largura * altura < 100_000:
            continue
        try:
            pix = pymupdf.Pixmap(doc, xref)
            if pix.alpha or pix.n - pix.alpha not in (1, 3):
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)  # CMYK etc. → RGB
                if pix.alpha:
                    continue
            modo = "L" if pix.n == 1 else "RGB"
            imagem = Image.frombytes(modo, (pix.width, pix.height), pix.samples)

            if dpi > dpi_limite:
                fator = dpi_alvo / dpi
                novo = (max(1, round(pix.width * fator)), max(1, round(pix.height * fator)))
                imagem = imagem.resize(novo, Image.LANCZOS)

            buffer = io.BytesIO()
            imagem.save(buffer, "JPEG", quality=qualidade, optimize=True)
            tamanho_atual = len(doc.xref_stream_raw(xref) or b"")
            if buffer.tell() < tamanho_atual:
                # Troca o conteúdo no próprio objeto da imagem: todas as
                # páginas que a usam passam a ver a versão nova, sem cópias.
                doc.update_stream(xref, buffer.getvalue(), compress=0)
                for chave in ("DecodeParms", "Decode", "Intent"):
                    doc.xref_set_key(xref, chave, "null")
                doc.xref_set_key(xref, "Filter", "/DCTDecode")
                doc.xref_set_key(xref, "Width", str(imagem.width))
                doc.xref_set_key(xref, "Height", str(imagem.height))
                doc.xref_set_key(xref, "BitsPerComponent", "8")
                doc.xref_set_key(
                    xref, "ColorSpace", "/DeviceGray" if modo == "L" else "/DeviceRGB"
                )
        except Exception:  # noqa: BLE001 — imagem exótica: deixa como está
            continue


def processar_pdfs(arquivos: list[str], destino: str, nivel: int | None, fila) -> int:
    """Lê, (opcionalmente) comprime e junta os PDFs, salvando em `destino`.

    Roda em um processo separado: o PyMuPDF segura o interpretador durante o
    trabalho pesado e, numa thread comum, isso congelaria a janela. O
    progresso volta para a janela pela `fila`.

    Usa o PyMuPDF (e não o pypdf) porque ele abre PDFs enormes, com imagens de
    centenas de MB guardadas sem compressão, e repara arquivos com a
    estrutura danificada — situações em que o pypdf desiste.

    Cada arquivo é comprimido ANTES de entrar no PDF final, então o programa
    nunca precisa montar o documento inteiro sem compressão na memória.
    """
    import pymupdf

    saida = pymupdf.open()
    try:
        total = len(arquivos)
        for i, caminho in enumerate(arquivos, start=1):
            nome = os.path.basename(caminho)
            fila.put(("arquivo", i - 1, nome))
            try:
                doc = pymupdf.open(caminho, filetype="pdf")
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"Falha ao ler “{nome}”: {e}") from e
            try:
                if doc.needs_pass and not doc.authenticate(""):
                    raise RuntimeError(f"Falha ao ler “{nome}”: arquivo protegido por senha")
                if nivel is not None:
                    _, dpi_limite, dpi_alvo, qualidade = NIVEIS_COMPRESSAO[nivel]
                    recomprimir_imagens(doc, dpi_limite, dpi_alvo, qualidade)
                saida.insert_pdf(doc)
            finally:
                doc.close()
            fila.put(("arquivo", i, nome))

        fila.put(("etapa", f"Salvando o PDF final ({len(saida)} páginas)…"))
        paginas = len(saida)
        saida.save(
            destino,
            garbage=3,          # remove objetos sem uso
            deflate=True,       # comprime (sem perda) o que estiver guardado cru
            use_objstms=1,      # agrupa objetos pequenos em fluxos compactados
        )
        return paginas
    finally:
        saida.close()


class MergeWorker(QObject):
    """Coordena o processamento em segundo plano para a janela não travar."""

    progresso = Signal(int, str)            # (arquivos concluídos, nome do arquivo)
    etapa = Signal(str)                     # texto da etapa atual (ex.: salvando)
    concluido = Signal(str, int, int, int)  # (saída, páginas, bytes antes, bytes depois)
    erro = Signal(str)

    def __init__(self, arquivos: list[str], destino: str, nivel: int | None):
        super().__init__()
        self.arquivos = arquivos
        self.destino = destino
        self.nivel = nivel  # None = sem compressão

    def run(self):
        # Salva primeiro num arquivo temporário na mesma pasta e só troca no
        # final: se der erro no meio, nenhum arquivo pela metade fica para trás.
        temporario = self.destino + ".parcial"
        try:
            antes = sum(os.path.getsize(c) for c in self.arquivos)
            with multiprocessing.Manager() as gerente:
                fila = gerente.Queue()
                with ProcessPoolExecutor(max_workers=1) as executor:
                    tarefa = executor.submit(
                        processar_pdfs, self.arquivos, temporario, self.nivel, fila
                    )
                    while True:
                        try:
                            self._repassar(fila.get(timeout=0.2))
                        except queue.Empty:
                            if tarefa.done():
                                break
                    while not fila.empty():
                        self._repassar(fila.get())
                    paginas = tarefa.result()
            os.replace(temporario, self.destino)
            self.concluido.emit(self.destino, paginas, antes, os.path.getsize(self.destino))
        except Exception as e:  # noqa: BLE001
            self.erro.emit(str(e) or e.__class__.__name__)
        finally:
            if os.path.exists(temporario):
                try:
                    os.remove(temporario)
                except OSError:
                    pass

    def _repassar(self, mensagem):
        tipo, *dados = mensagem
        if tipo == "arquivo":
            self.progresso.emit(*dados)
        elif tipo == "etapa":
            self.etapa.emit(*dados)


class ListaPdfs(QListWidget):
    """Lista que aceita arrastar PDFs do Explorer e reordenar arrastando."""

    arquivos_soltos = Signal(list)

    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAcceptDrops(True)
        self.setAlternatingRowColors(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            caminhos = []
            for url in event.mimeData().urls():
                p = url.toLocalFile()
                if os.path.isdir(p):
                    caminhos += sorted(
                        os.path.join(p, f) for f in os.listdir(p) if f.lower().endswith(".pdf")
                    )
                elif p.lower().endswith(".pdf"):
                    caminhos.append(p)
            self.arquivos_soltos.emit(caminhos)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class JanelaPrincipal(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Juntar PDFs")
        self.resize(640, 520)
        self.thread = None
        self.worker = None

        titulo = QLabel("<b>Juntar PDFs</b>")
        titulo.setStyleSheet("font-size: 18px;")
        dica = QLabel("Adicione os arquivos (ou arraste-os para a lista) e organize a ordem final. "
                      "Para só comprimir, adicione um único PDF.")
        dica.setWordWrap(True)
        dica.setStyleSheet("color: gray;")

        self.lista = ListaPdfs()
        self.lista.arquivos_soltos.connect(self.adicionar_caminhos)
        self.lista.model().rowsInserted.connect(self.atualizar_resumo)
        self.lista.model().rowsRemoved.connect(self.atualizar_resumo)

        self.btn_adicionar = QPushButton("Adicionar PDFs…")
        self.btn_subir = QPushButton("▲ Subir")
        self.btn_descer = QPushButton("▼ Descer")
        self.btn_remover = QPushButton("Remover")
        self.btn_limpar = QPushButton("Limpar")
        self.btn_ordenar = QPushButton("Ordenar A–Z")

        self.btn_adicionar.clicked.connect(self.escolher_arquivos)
        self.btn_subir.clicked.connect(lambda: self.mover(-1))
        self.btn_descer.clicked.connect(lambda: self.mover(1))
        self.btn_remover.clicked.connect(self.remover)
        self.btn_limpar.clicked.connect(self.lista.clear)
        self.btn_ordenar.clicked.connect(self.ordenar)

        barra = QHBoxLayout()
        for b in (self.btn_adicionar, self.btn_subir, self.btn_descer,
                  self.btn_remover, self.btn_ordenar, self.btn_limpar):
            barra.addWidget(b)

        self.chk_comprimir = QCheckBox("Comprimir o PDF final")
        self.chk_comprimir.setToolTip(
            "Reduz a resolução e recomprime as imagens (páginas digitalizadas, fotos).\n"
            "Texto digital continua nítido. Se não houver ganho, o arquivo sai sem compressão."
        )
        self.cmb_nivel = QComboBox()
        for rotulo, *_ in NIVEIS_COMPRESSAO:
            self.cmb_nivel.addItem(rotulo)
        self.cmb_nivel.setCurrentIndex(NIVEL_PADRAO)
        self.cmb_nivel.setEnabled(False)
        self.chk_comprimir.toggled.connect(self.cmb_nivel.setEnabled)
        self.chk_comprimir.toggled.connect(self.atualizar_resumo)

        linha_compressao = QHBoxLayout()
        linha_compressao.addWidget(self.chk_comprimir)
        linha_compressao.addWidget(self.cmb_nivel)
        linha_compressao.addStretch(1)

        self.resumo = QLabel("Nenhum arquivo adicionado.")
        self.progresso = QProgressBar()
        self.progresso.setVisible(False)

        self.btn_juntar = QPushButton("Juntar e salvar…")
        self.btn_juntar.setMinimumHeight(40)
        self.btn_juntar.setStyleSheet("font-weight: bold;")
        self.btn_juntar.clicked.connect(self.juntar)

        layout = QVBoxLayout(self)
        layout.addWidget(titulo)
        layout.addWidget(dica)
        layout.addLayout(barra)
        layout.addWidget(self.lista, 1)
        layout.addLayout(linha_compressao)
        layout.addWidget(self.resumo)
        layout.addWidget(self.progresso)
        layout.addWidget(self.btn_juntar)

    # ---------- Lista ----------
    def caminhos(self) -> list[str]:
        return [self.lista.item(i).data(Qt.UserRole) for i in range(self.lista.count())]

    def escolher_arquivos(self):
        arquivos, _ = QFileDialog.getOpenFileNames(self, "Selecionar PDFs", "", "PDF (*.pdf)")
        self.adicionar_caminhos(arquivos)

    def adicionar_caminhos(self, caminhos: list[str]):
        for c in caminhos:
            try:
                tamanho = formatar_tamanho(os.path.getsize(c))
            except OSError:
                tamanho = "?"
            item = QListWidgetItem(f"{os.path.basename(c)}   ({tamanho})")
            item.setData(Qt.UserRole, c)
            item.setToolTip(c)
            self.lista.addItem(item)

    def mover(self, direcao: int):
        linhas = sorted({self.lista.row(i) for i in self.lista.selectedItems()},
                        reverse=direcao > 0)
        for linha in linhas:
            nova = linha + direcao
            if 0 <= nova < self.lista.count():
                item = self.lista.takeItem(linha)
                self.lista.insertItem(nova, item)
                item.setSelected(True)

    def remover(self):
        for item in self.lista.selectedItems():
            self.lista.takeItem(self.lista.row(item))

    def ordenar(self):
        self.lista.sortItems(Qt.AscendingOrder)

    def atualizar_resumo(self, *_):
        n = self.lista.count()
        comprimir = self.chk_comprimir.isChecked()
        if n == 1 and comprimir:
            self.btn_juntar.setText("Comprimir e salvar…")
        elif comprimir:
            self.btn_juntar.setText("Juntar, comprimir e salvar…")
        else:
            self.btn_juntar.setText("Juntar e salvar…")
        if n == 0:
            self.resumo.setText("Nenhum arquivo adicionado.")
            return
        total = sum(os.path.getsize(c) for c in self.caminhos() if os.path.exists(c))
        self.resumo.setText(f"{n} arquivo(s) • {formatar_tamanho(total)} no total")

    # ---------- Junção ----------
    def juntar(self):
        arquivos = self.caminhos()
        comprimir = self.chk_comprimir.isChecked()
        if not arquivos or (len(arquivos) < 2 and not comprimir):
            QMessageBox.information(
                self, "Juntar PDFs",
                "Adicione pelo menos dois arquivos para juntar, "
                "ou marque “Comprimir” para comprimir um único PDF.",
            )
            return

        if len(arquivos) == 1:
            base = os.path.splitext(os.path.basename(arquivos[0]))[0]
            sugestao = os.path.join(os.path.dirname(arquivos[0]), f"{base}_comprimido.pdf")
            titulo = "Salvar PDF comprimido"
        else:
            sugestao = os.path.join(os.path.dirname(arquivos[0]), "PDF_unido.pdf")
            titulo = "Salvar PDF unido"
        destino, _ = QFileDialog.getSaveFileName(self, titulo, sugestao, "PDF (*.pdf)")
        if not destino:
            return
        if not destino.lower().endswith(".pdf"):
            destino += ".pdf"
        if os.path.abspath(destino) in map(os.path.abspath, arquivos):
            QMessageBox.warning(self, "Juntar PDFs",
                                "O arquivo de saída não pode ser um dos arquivos de entrada.")
            return

        self.definir_ocupado(True, len(arquivos))
        self.thread = QThread()
        nivel = self.cmb_nivel.currentIndex() if comprimir else None
        self.worker = MergeWorker(arquivos, destino, nivel)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progresso.connect(self.ao_progredir)
        self.worker.etapa.connect(self.ao_mudar_etapa)
        self.worker.concluido.connect(self.ao_concluir)
        self.worker.erro.connect(self.ao_errar)
        self.worker.concluido.connect(self.thread.quit)
        self.worker.erro.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def definir_ocupado(self, ocupado: bool, total: int = 0):
        for w in (self.btn_adicionar, self.btn_subir, self.btn_descer, self.btn_remover,
                  self.btn_limpar, self.btn_ordenar, self.btn_juntar, self.lista,
                  self.chk_comprimir):
            w.setEnabled(not ocupado)
        self.cmb_nivel.setEnabled(not ocupado and self.chk_comprimir.isChecked())
        self.progresso.setVisible(ocupado)
        if ocupado:
            self.progresso.setRange(0, total)
            self.progresso.setValue(0)

    def ao_progredir(self, concluidos: int, nome: str):
        total = self.progresso.maximum()
        self.progresso.setValue(concluidos)
        if concluidos < total:
            acao = "Comprimindo" if self.chk_comprimir.isChecked() else "Lendo"
            self.progresso.setFormat(f"{concluidos}/{total} — {acao} “{nome}”…")
        else:
            self.progresso.setFormat(f"{concluidos}/{total}")

    def ao_mudar_etapa(self, texto: str):
        # Barra "ocupada" (animada): a compressão não tem progresso por página.
        self.progresso.setRange(0, 0)
        self.progresso.setFormat(texto)
        self.resumo.setText(texto)

    def ao_concluir(self, destino: str, paginas: int, antes: int, depois: int):
        self.definir_ocupado(False)
        self.atualizar_resumo()
        detalhe = ""
        if self.chk_comprimir.isChecked():
            if depois < antes:
                reducao = (1 - depois / antes) * 100
                detalhe = (f"\nTamanho: {formatar_tamanho(antes)} → {formatar_tamanho(depois)} "
                           f"({reducao:.0f}% menor)")
            else:
                detalhe = (f"\nO tamanho quase não mudou ({formatar_tamanho(depois)}): "
                           f"os arquivos têm poucas imagens para comprimir.")
        resp = QMessageBox.question(
            self, "Concluído",
            f"PDF criado com {paginas} página(s):\n{destino}{detalhe}\n\nDeseja abrir a pasta?",
        )
        if resp == QMessageBox.Yes:
            abrir_pasta(os.path.dirname(destino))

    def ao_errar(self, mensagem: str):
        self.definir_ocupado(False)
        self.atualizar_resumo()
        QMessageBox.critical(self, "Erro", mensagem)


def abrir_pasta(pasta: str):
    if sys.platform.startswith("win"):
        os.startfile(pasta)  # noqa: S606
    elif sys.platform == "darwin":
        os.system(f'open "{pasta}"')
    else:
        os.system(f'xdg-open "{pasta}"')


if __name__ == "__main__":
    # Obrigatório para a compressão em processo separado funcionar no .exe (PyInstaller).
    multiprocessing.freeze_support()
    app = QApplication(sys.argv)
    janela = JanelaPrincipal()
    janela.show()
    sys.exit(app.exec())
