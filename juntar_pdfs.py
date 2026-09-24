"""
Juntar PDFs — aplicativo desktop para unir vários PDFs em um só.
Sem limites de quantidade, tamanho ou uso. Tudo roda localmente.

Requisitos:
    pip install PySide6 pypdf

Executar:
    python juntar_pdfs.py
"""

import os
import sys

from pypdf import PdfReader, PdfWriter
from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
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


class MergeWorker(QObject):
    """Faz a junção em segundo plano para a janela não travar com arquivos grandes."""

    progresso = Signal(int, str)      # (índice concluído, nome do arquivo)
    concluido = Signal(str, int)      # (caminho de saída, total de páginas)
    erro = Signal(str)

    def __init__(self, arquivos: list[str], destino: str):
        super().__init__()
        self.arquivos = arquivos
        self.destino = destino

    def run(self):
        writer = PdfWriter()
        try:
            for i, caminho in enumerate(self.arquivos, start=1):
                nome = os.path.basename(caminho)
                try:
                    reader = PdfReader(caminho)
                    if reader.is_encrypted:
                        # Tenta abrir PDFs protegidos só contra edição (senha vazia)
                        if not reader.decrypt(""):
                            raise ValueError("arquivo protegido por senha")
                    writer.append(reader)
                except Exception as e:  # noqa: BLE001
                    raise RuntimeError(f"Falha ao ler “{nome}”: {e}") from e
                self.progresso.emit(i, nome)

            total_paginas = len(writer.pages)
            with open(self.destino, "wb") as f:
                writer.write(f)
            self.concluido.emit(self.destino, total_paginas)
        except Exception as e:  # noqa: BLE001
            self.erro.emit(str(e))
        finally:
            writer.close()


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
        dica = QLabel("Adicione os arquivos (ou arraste-os para a lista) e organize a ordem final.")
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
        if n == 0:
            self.resumo.setText("Nenhum arquivo adicionado.")
            return
        total = sum(os.path.getsize(c) for c in self.caminhos() if os.path.exists(c))
        self.resumo.setText(f"{n} arquivo(s) • {formatar_tamanho(total)} no total")

    # ---------- Junção ----------
    def juntar(self):
        arquivos = self.caminhos()
        if len(arquivos) < 2:
            QMessageBox.information(self, "Juntar PDFs", "Adicione pelo menos dois arquivos.")
            return

        sugestao = os.path.join(os.path.dirname(arquivos[0]), "PDF_unido.pdf")
        destino, _ = QFileDialog.getSaveFileName(self, "Salvar PDF unido", sugestao, "PDF (*.pdf)")
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
        self.worker = MergeWorker(arquivos, destino)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progresso.connect(self.ao_progredir)
        self.worker.concluido.connect(self.ao_concluir)
        self.worker.erro.connect(self.ao_errar)
        self.worker.concluido.connect(self.thread.quit)
        self.worker.erro.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def definir_ocupado(self, ocupado: bool, total: int = 0):
        for w in (self.btn_adicionar, self.btn_subir, self.btn_descer, self.btn_remover,
                  self.btn_limpar, self.btn_ordenar, self.btn_juntar, self.lista):
            w.setEnabled(not ocupado)
        self.progresso.setVisible(ocupado)
        if ocupado:
            self.progresso.setRange(0, total)
            self.progresso.setValue(0)

    def ao_progredir(self, i: int, nome: str):
        self.progresso.setValue(i)
        self.progresso.setFormat(f"{i}/{self.progresso.maximum()} — {nome}")

    def ao_concluir(self, destino: str, paginas: int):
        self.definir_ocupado(False)
        resp = QMessageBox.question(
            self, "Concluído",
            f"PDF criado com {paginas} página(s):\n{destino}\n\nDeseja abrir a pasta?",
        )
        if resp == QMessageBox.Yes:
            abrir_pasta(os.path.dirname(destino))

    def ao_errar(self, mensagem: str):
        self.definir_ocupado(False)
        QMessageBox.critical(self, "Erro", mensagem)


def abrir_pasta(pasta: str):
    if sys.platform.startswith("win"):
        os.startfile(pasta)  # noqa: S606
    elif sys.platform == "darwin":
        os.system(f'open "{pasta}"')
    else:
        os.system(f'xdg-open "{pasta}"')


if __name__ == "__main__":
    app = QApplication(sys.argv)
    janela = JanelaPrincipal()
    janela.show()
    sys.exit(app.exec())
