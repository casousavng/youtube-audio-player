# 🎧 YouTube Simples Player (SwiftBar Plugin)

> Um leitor de áudio em background do YouTube ultra-leve e otimizado para o macOS (Apple Silicon M1/M2/M3), integrado diretamente na sua barra de menus usando o SwiftBar.

![Demonstração da Barra de Menus](menu_bar.png)

---

## ✨ Características Principais

* **🎧 Áudio em Background Puro:** Remove a componente de vídeo, focando-se apenas na transmissão de áudio.
* 🚀 **Otimizado para Apple Silicon:** Utiliza descodificadores nativos de hardware do macOS via `mpv`, mantendo o consumo de recursos ridiculamente baixo.
* ⏱️ **Visualização de Progresso Dinâmica:** Barra de progresso visual simulada no menu e no terminal.
* 📋 **Fácil Adição de Links:** Adicione URLs copiando para o clipboard (`Clipboard`) ou colando na janela nativa do macOS.
* 🎛️ **Controlo Completo na Barra:** Play/Pause, Next/Prev, Mute, Limpar Fila e saltar diretamente para qualquer faixa na fila.
* 🧹 **Persistência da Fila (Queue):** Salva o progresso e a playlist atual de forma a não perder nada ao reiniciar o leitor.
* 🛠️ **Dashboard TUI Inteligente:** Dashboard interativo em Terminal com **auto-redimensionamento dinâmico de janela** (70x22) para uma exibição impecável.
* 📦 **Assistente Automático de Dependências:** Instalação inteligente do `mpv` e `yt-dlp` através de Homebrew com um único clique.

---

## 📊 Validação de Consumo e Eficiência

Comparação direta dos consumos de recursos no macOS de um áudio em background ativo contra outras aplicações de desenvolvimento padrão:

| Aplicação / Processo | Uso de CPU (%) | Uso de RAM (Física - RSS) | Nota sobre o Impacto |
| :--- | :---: | :---: | :--- |
| **YouTube no Browser (Brave/Chrome)** | ~10% - 25% | ~150 MB - 350 MB | Alto (Processamento gráfico de vídeo oculto) |
| **SwiftBar (Menu Bar App)** | ~5.0 % | ~30 MB | Muito Baixo (Integração de Menus) |
| **YouTube Simples Player (`mpv`)** | 🟢 **1.5% - 3.5%** | 🟢 **~34.7 MB** | **Extremamente Baixo (Praticamente Invisível)** |

---

## 🚀 Como Instalar e Configurar (Guia Rápido)

### 1. Pré-requisitos
Certifique-se de que tem o **Homebrew** instalado no seu Mac. Se não tiver, abra o Terminal e instale-o executando:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

E instale o **SwiftBar** (o gestor de plugins de barra de menus):
```bash
brew install --cask swiftbar
```

### 2. Instalação do Plugin
1. Crie ou escolha uma pasta para os seus plugins do SwiftBar (ex: `~/swiftbar-plugins`).
2. Descarregue o script `youtube_audio.5s.py` e coloque-o nessa pasta.
3. Torne o script executável através do Terminal:
   ```bash
   chmod +x ~/swiftbar-plugins/youtube_audio.5s.py
   ```

### 3. Execução e Instalação de Dependências
1. Abra o **SwiftBar** e selecione a pasta criada (`~/swiftbar-plugins`).
2. O ícone de auscultadores `🎧` surgirá na barra de menus, indicando que faltam dependências.
3. Clique no menu e selecione **`Instalar mpv e yt-dlp via Homebrew`**.
4. O script instalará o `mpv` e o `yt-dlp` de forma totalmente automática.

*Pronto! Já pode começar a colar links do YouTube e ouvir áudio de alta qualidade em background sem gastar bateria!*

---

## 🛠️ Dashboard TUI Interativo (Terminal)

Ao clicar em **`Abrir Dashboard TUI Interativo`** no menu do SwiftBar, uma janela do Terminal abrir-se-á e será **automaticamente redimensionada para 70x22** de forma a manter o layout perfeito.

### Atalhos no Terminal:
* `[Espaço]` - Play / Pausa
* `[M]` - Mute / Unmute
* `[N]` - Próxima Faixa
* `[P]` - Faixa Anterior
* `[A]` - Adicionar URL Manualmente
* `[C]` - Adicionar do Clipboard
* `[X]` - Limpar Toda a Fila
* `[S]` - Sair e Parar Player completamente
* `[Q]` - Fechar o terminal (o leitor continua em background)

---

## 📄 Licença

Este projeto está licenciado sob a licença MIT - consulte o ficheiro [LICENSE](LICENSE) para mais detalhes.
