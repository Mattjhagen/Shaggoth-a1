# R510 setup: Tailscale SSH, opencode + Big Pickle, and training Shaggoth

This cloud session cannot reach your Tailnet (no Tailscale in the sandbox), so
the R510 steps below are written to run **on the R510 itself** — either from
your laptop over Tailscale SSH, or via opencode running on the server.

## 1. Connect over Tailscale SSH

On the R510 (one-time, if not already done):

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh          # advertises Tailscale SSH on this machine
```

From any of your devices on the Tailnet:

```bash
tailscale status                  # find the R510's hostname/IP
tailscale ssh <user>@r510         # or: ssh <user>@<tailnet-name>
```

Tailscale SSH authenticates with your Tailnet identity — no key files to
manage, and the connection works from anywhere.

## 2. Run opencode with Big Pickle

[opencode](https://opencode.ai) is a terminal AI coding agent; **Big Pickle**
is its free hosted model — handy for iterating on this repo directly on the
server.

```bash
# on the R510
curl -fsSL https://opencode.ai/install | bash
cd ~/Shaggoth-a1        # clone first if needed (step 3)
opencode
# then: /models → select "Big Pickle" (free tier) → chat/build away
```

Tip: run it inside `tmux` so long sessions survive SSH disconnects:
`tmux new -s opencode`.

## 3. Get Shaggoth onto the R510

```bash
git clone https://github.com/Mattjhagen/Shaggoth-a1.git
cd Shaggoth-a1
python3 -m unittest discover -s tests    # should pass with zero deps
python3 -m shaggoth chat                 # try it
```

## 4. Train the models

Markov (instant, no dependencies):

```bash
python3 -m shaggoth train --corpus data/corpus/starter.txt
```

TinyGPT (the real from-scratch transformer). The R510 is CPU-only, so install
the CPU wheel of PyTorch:

```bash
python3 -m pip install torch --index-url https://download.pytorch.org/whl/cpu

# quick sanity run (~minutes on CPU):
python3 -m shaggoth train --model tinygpt --corpus data/corpus/starter.txt \
    --steps 500 --out data/tinygpt.pt

# real overnight run with a bigger corpus (drop .txt files into data/corpus/):
cat data/corpus/*.txt > /tmp/full_corpus.txt
python3 -m shaggoth train --model tinygpt --corpus /tmp/full_corpus.txt \
    --steps 20000 --out data/tinygpt.pt
```

Corpus ideas: Project Gutenberg public-domain books, your own writing/notes,
exported chat logs. More (and more conversational) text → better model.

## 5. Run the API as a service

`/etc/systemd/system/shaggoth.service`:

```ini
[Unit]
Description=Shaggoth conversational AI API
After=network.target

[Service]
User=%i
WorkingDirectory=/home/<user>/Shaggoth-a1
ExecStart=/usr/bin/python3 -m shaggoth serve --host 0.0.0.0 --port 8420
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now shaggoth
```

**Security note:** binding `0.0.0.0` is safe *only* because the Tailnet is the
network boundary — do not port-forward 8420 to the internet. The Phase-1 API
has no auth (that's Phase 2 in the roadmap). To reach it from your phone,
install Tailscale on the phone and point the app at
`http://r510:8420` (or use `tailscale serve` for HTTPS).

## 6. Nightly retraining (optional)

```bash
crontab -e
# retrain markov on the full corpus every night at 03:00
0 3 * * * cd ~/Shaggoth-a1 && cat data/corpus/*.txt | python3 -m shaggoth train --corpus /dev/stdin
```

(TinyGPT overnight runs are better launched manually or via a systemd timer
once you've picked step counts that fit the machine.)
