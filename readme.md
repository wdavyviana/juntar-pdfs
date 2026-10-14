# 📎 Juntar PDFs

**Una vários PDFs em um só e comprima o resultado, direto no seu computador: sem limites, sem cadastro e sem enviar seus arquivos para a internet.**

Uma alternativa simples ao modo gratuito de sites como o iLovePDF. Aqui você junta quantos arquivos quiser, do tamanho que quiser, quantas vezes quiser.

![Windows](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6?logo=windows&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![Grátis](https://img.shields.io/badge/uso-100%25%20gratuito-2ea44f)

---

## ✨ O que ele faz

| | |
|---|---|
| ♾️ **Sem limites** | Quantidade de arquivos, tamanho e número de usos ilimitados. Junta até PDFs de centenas de MB e repara arquivos danificados |
| 🔒 **Privado** | Tudo acontece no seu computador. Nenhum arquivo é enviado para a internet |
| 🖱️ **Arrastar e soltar** | Arraste PDFs, ou pastas inteiras, direto para a janela |
| 🗜️ **Compressão** | Reduz o tamanho de PDFs digitalizados e com fotos, em 3 níveis (Leve, Recomendada, Forte). Também comprime um único PDF, sem juntar |
| ↕️ **Ordem do seu jeito** | Reorganize arrastando os arquivos, com os botões ▲ ▼ ou em ordem alfabética (A–Z) |
| 📊 **Barra de progresso** | Acompanhe a junção, sem travar, mesmo com arquivos grandes |
| 📂 **Abre a pasta no final** | Ao terminar, mostra quantas páginas o PDF tem e abre a pasta onde ele foi salvo |

---

## ⬇️ Como baixar e usar (para qualquer pessoa)

> Não precisa instalar nada. É só baixar e abrir.

### 1. Baixe o programa
Acesse a página de **[Releases](https://github.com/wdavyviana/juntar-pdfs/releases/latest)** e clique em **`Juntar PDFs.exe`** para baixar.

### 2. Abra o arquivo
Dê **dois cliques** no `Juntar PDFs.exe`. Ele normalmente fica na pasta **Downloads**.

### 3. Libere na primeira vez (só uma vez)
O Windows pode mostrar a tela azul **"O Windows protegeu o computador"**.
Isso acontece porque o programa não tem assinatura digital paga, e **não significa que tenha vírus**.

➡️ Clique em **Mais informações** → **Executar assim mesmo**.

### 4. Pronto! Agora é só usar
1. Clique em **Adicionar PDFs…** ou arraste os arquivos para a janela
2. Organize a ordem como preferir
3. *(Opcional)* Marque **Comprimir o PDF final** e escolha o nível
4. Clique em **Juntar e salvar…** e escolha onde salvar
5. Pronto: seu PDF está na pasta escolhida 🎉

> 🗜️ **Só quer comprimir um arquivo?** Adicione um único PDF, marque **Comprimir o PDF final** e clique em **Comprimir e salvar…**

> 💡 **Dica:** clique com o botão direito no `.exe` → **Enviar para** → **Área de trabalho (criar atalho)** para abrir sempre com um clique.

---

## ❓ Dúvidas comuns

<details>
<summary><b>O programa demora para abrir. É normal?</b></summary>

Sim. Por ser um arquivo único, ele leva alguns segundos para abrir. Depois disso, funciona normalmente.
</details>

<details>
<summary><b>Qual nível de compressão usar?</b></summary>

- **Leve:** reduz as imagens para 200 DPI. Use quando precisar de qualidade de impressão.
- **Recomendada:** 150 DPI. Ótima leitura na tela e boa impressão. É o padrão.
- **Forte:** 100 DPI. Menor arquivo possível, ainda legível na tela.

A compressão age nas **imagens** (páginas digitalizadas, fotos). Texto digital continua nítido. Se o PDF quase não tiver imagens, ele não vai diminuir muito, e o programa avisa e salva sem alteração.
</details>

<details>
<summary><b>Meu antivírus bloqueou o arquivo. E agora?</b></summary>

Alguns antivírus desconfiam de programas criados com Python (PyInstaller) por padrão. Isso é um falso alarme conhecido. Você pode liberar o arquivo nas configurações do antivírus, ou conferir o código-fonte, que está todo aberto aqui no repositório.
</details>

<details>
<summary><b>Apareceu "arquivo protegido por senha".</b></summary>

O programa não consegue abrir PDFs protegidos por senha de abertura. Remova a senha do arquivo e tente de novo.
</details>

<details>
<summary><b>Funciona no Mac ou no Linux?</b></summary>

O `.exe` é só para Windows. No Mac ou no Linux, rode direto pelo Python (veja a seção abaixo).
</details>

---

## 🛠️ Para desenvolvedores

### Rodar pelo código-fonte
Requer **Python 3.10+**.

```bash
git clone https://github.com/wdavyviana/juntar-pdfs.git
cd juntar-pdfs
pip install -r requirements.txt
python juntar_pdfs.py
```

### Gerar o executável (.exe)
```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "Juntar PDFs" juntar_pdfs.py
```
O arquivo fica em `dist/Juntar PDFs.exe`.

### Publicar uma nova versão
1. Gere o `.exe` de novo, com o comando acima
2. No GitHub, vá em **Releases** → **Draft a new release**
3. Crie uma tag (ex.: `v1.0.0`), escreva o que mudou e **anexe o `Juntar PDFs.exe`**
4. Clique em **Publish release**

### Tecnologias
- [PySide6](https://doc.qt.io/qtforpython-6/): interface gráfica (Qt)
- [PyMuPDF](https://pymupdf.readthedocs.io/): leitura, reparo e junção dos PDFs (inclusive arquivos enormes)
- [Pillow](https://python-pillow.org/): compressão das imagens
- [PyInstaller](https://pyinstaller.org/): geração do executável

### Estrutura
```
juntar-pdfs/
├── juntar_pdfs.py      # aplicativo completo
├── requirements.txt    # dependências
├── .gitignore
└── README.md
```

---

Feito por **[Wendel Davy](https://github.com/wdavyviana)** 🌊 Fortaleza, CE
