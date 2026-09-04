# SPDX-License-Identifier: LicenseRef-Pixelith-EULA-1.0
# Copyright (c) 2026 PGA Tech Solutions. Free for personal use within the
# stated allowance; beyond it, and for all commercial use, a paid licence
# is required. See LICENSE.
"""Command line interface: `python -m pixelith ...`"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import __version__, license_info
from .config import (MODELS, OUTPUT_DIR, PRESETS, WORK_DIR, UpscaleSettings,
                     resolve_preset)
from .engine import Cancelled, Engine, available_providers, choose_providers
from . import licensing, watermark
from .models import ensure, status as model_status
from .pipeline import estimate_seconds, human_time, plan, upscale_image
from .video import VideoError, have_ffmpeg, probe, upscale_video

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".heic"}


IS_TTY = sys.stdout.isatty()


def _bar(frac: float, width: int = 32) -> str:
    filled = int(frac * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


def cmd_serve(args: argparse.Namespace) -> int:
    from .compat import lan_address, summary
    from .server import serve

    host = "0.0.0.0" if args.lan else args.host
    info = summary()

    print(f"Pixelith {__version__} on {info['os']} ({info['arch']}), "
          f"{info['cpus']} cores, {info['ram_gb']} GB")
    print(f"  this computer   http://127.0.0.1:{args.port}")
    if args.lan:
        ip = lan_address()
        if ip:
            print(f"  phone / tablet  http://{ip}:{args.port}")
            print("     Open that on any device on the same Wi-Fi. No app needed.")
        else:
            print("  phone / tablet  could not detect a LAN address; check your network")
        print("     No sign-in and no account: anyone on this network can "
              "just open it.")
        print("     Use --lan on a network you trust, not on public Wi-Fi.")
    else:
        print("  (use --lan to reach it from a phone or tablet on the same Wi-Fi)")
    print(f"Results are written to {OUTPUT_DIR}")
    serve(host, args.port, args.reload)
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    from .compat import summary

    info = summary()
    print(f"Pixelith {__version__}")
    print(f"  platform   : {info['os']} {info['arch']}, python {info['python']}")
    print(f"  hardware   : {info['cpus']} cores, {info['ram_gb']} GB RAM")
    print(f"  output dir : {OUTPUT_DIR}")
    print(f"  ffmpeg     : {'yes' if have_ffmpeg() else 'NOT FOUND (video disabled)'}")
    print(f"  HEIC/HEIF  : {'yes' if info['heic'] else 'no (pip install pillow-heif)'}")
    print(f"  providers  : {', '.join(available_providers())}")
    lic = license_info()
    free = lic["free_allowance"]
    print(f"  license    : {lic['name']}")
    print(f"               free for personal use up to {free['images']} images "
          f"and {free['video_bytes'] // 1024**3} GB of video")
    print("               run 'pixelith license' for the full terms")
    print("\nModels:")
    for m in model_status():
        spec = MODELS[m["key"]]
        mark = "installed" if m["installed"] else f"not downloaded ({m['size_mb']} MB)"
        print(f"  {m['key']:8} {m['label']:34} x{m['scale']}  [{mark}]")
        print(f"           runs on {choose_providers(spec=spec)[0]}")
        print(f"           {m['notes']}")
    print("\nPresets: " + ", ".join(f"{k} ({v[0]}x{v[1]})" for k, v in PRESETS.items()))
    return 0


def cmd_license(args: argparse.Namespace) -> int:
    from . import CURRENCIES, TIERS, tier_price

    lic = license_info()
    print(f"{lic['name']}")
    print(f"{lic['copyright']}")
    print()
    print(f"  {'Tier':<12} {'India':>10} {'Elsewhere':>11}   What it covers")
    print(f"  {'-' * 12} {'-' * 10} {'-' * 11}   {'-' * 44}")
    for t in TIERS:
        print(f"  {t['name']:<12} {tier_price(t['key'], 'INR'):>10} "
              f"{tier_price(t['key'], 'USD'):>11}   {t['summary']}")
    print()
    from . import tier_total
    print(f"  Indian prices are exclusive of 18% GST: "
          f"{tier_price('personal','INR')} + GST = {tier_total('personal','INR')}, "
          f"{tier_price('commercial','INR')} + GST = {tier_total('commercial','INR')}.")
    print("  Paid by UPI, card or net banking; tax invoice issued.")
    print("  Elsewhere, local taxes are added at checkout.")
    print("  There is no separate payment-processing charge.")
    print()
    print("The free allowance is 100 still images and 1 GB of video input.")
    print("The two are independent - running out of one does not consume the")
    print("other. A single paid licence removes both, permanently; there is no")
    print("separate charge for images and video, and nothing to renew.")
    print()
    print("Charities, schools, universities and public bodies count as personal")
    print("use, however they are funded.")
    print()
    print("The allowance is measured on this machine, and Pixelith stops when")
    print("you reach it. Licence keys are verified offline. Nothing is ever")
    print("sent to us: no telemetry, no usage reports, no activation server.")
    print()
    print("Free-tier output carries an invisible provenance mark identifying")
    print("the tier and installation. It holds no personal information and is")
    print("never transmitted. A paid licence removes it. Read one back with")
    print("'pixelith verify <file>'.")
    print()
    print(f"  Full terms       {lic['url']}")
    print(f"  Buy a licence    {lic['commercial_contact']}")
    print()
    print("Bundled model weights are third-party works under the BSD 3-Clause")
    print("licence and are not covered by these terms; see NOTICE.md.")
    print(f"Versions 0.1.x were released under {lic['prior_license'].split(' (')[0]}")
    print("and keep those rights.")
    return 0


def _fmt_bytes(n: int) -> str:
    if n >= 1024**3:
        return f"{n / 1024**3:.2f} GB"
    if n >= 1024**2:
        return f"{n / 1024**2:.0f} MB"
    return f"{n / 1024:.0f} KB"


def cmd_status(args: argparse.Namespace) -> int:
    st = licensing.allowance_status()
    if st["licensed"]:
        holder = st["holder"] or "unnamed"
        print(f"Licensed: {st['tier']} - {holder}")
        print("  images   unlimited")
        print("  video    unlimited")
        print("  output   no watermark")
    else:
        print("Free tier")
        print(f"  images   {st['images_used']} of {st['images_limit']} used, "
              f"{st['images_remaining']} left")
        print(f"  video    {_fmt_bytes(st['video_bytes_used'])} of "
              f"{_fmt_bytes(st['video_bytes_limit'])} used, "
              f"{_fmt_bytes(st['video_bytes_remaining'])} left")
        print("  output   carries an invisible provenance mark")
        print()
        from . import tier_price
        print("  A licence removes both limits and the mark, permanently:")
        print(f"    {tier_price('personal','INR'):>8} / "
              f"{tier_price('personal','USD'):<6} personal, one person, all their devices")
        print(f"    {tier_price('commercial','INR'):>8} / "
              f"{tier_price('commercial','USD'):<6} commercial, one company")
        from . import COMMERCIAL_CONTACT
        print(f"    Buy one at {COMMERCIAL_CONTACT}, then run "
              f"'pixelith activate <key>'")
    if st["tampered"]:
        print()
        print("  Note: the usage record does not match its checksum. It has been")
        print("  edited or corrupted. Counting continues from what is there.")
    print(f"\n  install {st['install_id']}")
    return 0


def cmd_activate(args: argparse.Namespace) -> int:
    try:
        claims = licensing.activate(args.key)
    except licensing.LicenceError as exc:
        print(f"Could not activate: {exc}", file=sys.stderr)
        return 1
    print(f"Activated: {claims['tier']} licence for {claims.get('holder','')}")
    print("Limits removed, and output is no longer watermarked. Thank you.")
    return 0


def cmd_deactivate(args: argparse.Namespace) -> int:
    if licensing.deactivate():
        print("Licence removed from this machine. Back to the free tier.")
        return 0
    print("No licence was active on this machine.")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """Read the provenance mark out of an image."""
    import numpy as np
    from PIL import Image

    path = Path(args.file).expanduser()
    if not path.exists():
        print(f"no such file: {path}", file=sys.stderr)
        return 2
    with Image.open(path) as im:
        found = watermark.extract(np.asarray(im.convert("RGB")))
    if not found:
        print(f"{path.name}: no Pixelith mark found.")
        print("  Either it was not made by Pixelith, it was made under a paid")
        print("  licence, or the mark did not survive later editing.")
        return 1
    print(f"{path.name}: Pixelith mark found")
    print(f"  tier      {found['tier_name']}")
    print(f"  install   {found['install_id']}")
    print(f"  sequence  {found['sequence']}")
    if found["tier_name"] == "free":
        print("\n  This file was produced under the free tier, which does not")
        print("  permit commercial use.")
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    keys = args.models or list(MODELS)
    for key in keys:
        if key not in MODELS:
            print(f"unknown model {key!r}", file=sys.stderr)
            return 2
        last = [-1.0]

        def prog(frac: float, msg: str) -> None:
            step = 0.02 if IS_TTY else 0.25
            if frac - last[0] >= step or frac >= 1.0:
                last[0] = frac
                if IS_TTY:
                    print(f"\r  {_bar(frac)} {frac*100:5.1f}%  {msg}",
                          end="", flush=True)
                else:
                    print(f"  {frac*100:5.1f}%  {msg}", flush=True)

        ensure(MODELS[key], prog)
        print()
    return 0


def cmd_upscale(args: argparse.Namespace) -> int:
    src = Path(args.input).expanduser()
    if not src.exists():
        print(f"no such file: {src}", file=sys.stderr)
        return 2

    settings = UpscaleSettings(
        model=args.model, preset=args.preset, scale=args.scale,
        denoise=args.denoise, sharpen=args.sharpen, quality=args.quality,
        tile=args.tile,
    )
    spec = settings.resolved_model()
    is_video = src.suffix.lower() not in IMAGE_SUFFIXES

    if is_video:
        if not have_ffmpeg():
            print("FFmpeg is required for video. Install it and try again.",
                  file=sys.stderr)
            return 2
        info = probe(src)
        w, h, frames = info.width, info.height, max(1, info.frames)
    else:
        from PIL import Image, ImageOps
        with Image.open(src) as im:
            w, h = ImageOps.exif_transpose(im).size
        frames = 1

    p = plan(w, h, settings.preset, settings.scale, spec.scale)
    est = estimate_seconds(w, h, p, spec.key, frames=frames)

    if args.output:
        dest = Path(args.output).expanduser()
    else:
        ext = ".mp4" if is_video else (src.suffix if src.suffix.lower() in
                                       (".png", ".jpg", ".jpeg", ".webp") else ".png")
        dest = OUTPUT_DIR / f"{src.stem}_{p.out_width}x{p.out_height}{ext}"

    print(f"{src.name}: {w}x{h} -> {p.out_width}x{p.out_height} "
          f"({p.passes} network pass{'es' if p.passes != 1 else ''}, model '{spec.key}')")
    if is_video:
        print(f"  {frames} frames at {info.fps} fps")
    print(f"  estimated {human_time(est)}")
    print(f"  writing to {dest}")

    if est > 900 and not args.yes:
        reply = input("  This is a long job. Continue? [y/N] ").strip().lower()
        if reply not in ("y", "yes"):
            print("  aborted")
            return 1

    try:
        licensing.check_allowance("video" if is_video else "image",
                                  video_bytes=src.stat().st_size if is_video else 0)
    except licensing.AllowanceExceeded as exc:
        print(f"\n  {exc}", file=sys.stderr)
        return 3

    engine = Engine(spec, settings)
    print(f"  running on {engine.provider}")
    started = time.time()
    state = {"last": 0.0}

    def show(frac: float, msg: str, extra: dict | None = None) -> None:
        """Animate in a terminal; emit sparse lines when piped to a file or CI."""
        now = time.time()
        min_gap = 0.1 if IS_TTY else 5.0
        if now - state["last"] < min_gap and frac < 1.0:
            return
        state["last"] = now
        elapsed = now - started
        eta = (extra or {}).get("eta_seconds")
        if eta is None and frac > 0.02:
            eta = elapsed / frac - elapsed
        tail = f"  eta {human_time(eta)}" if eta else ""
        if IS_TTY:
            print(f"\r  {_bar(frac)} {frac*100:5.1f}%  {msg}{tail}   ",
                  end="", flush=True)
        else:
            print(f"  {frac*100:5.1f}%  {msg}{tail}", flush=True)

    try:
        if is_video:
            report = upscale_video(
                src, dest, settings, work_dir=WORK_DIR / f"cli_{src.stem}",
                engine=engine, progress=show,
            )
        else:
            report = upscale_image(
                src, dest, settings, engine=engine,
                progress=lambda f, m: show(f, m, None),
            )
    except Cancelled:
        print("\n  cancelled")
        return 1
    except licensing.AllowanceExceeded as exc:
        print(f"\n\n  {exc}", file=sys.stderr)
        return 3
    except (VideoError, ValueError) as exc:
        print(f"\n  failed: {exc}", file=sys.stderr)
        return 1

    print(f"\n  done in {report['elapsed']}s -> {dest}")
    if report.get("seconds_per_frame"):
        print(f"  {report['seconds_per_frame']}s per frame")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="pixelith",
        description="Upscale images and video with AI, locally, up to 8K.",
    )
    ap.add_argument("--version", action="version", version=f"pixelith {__version__}")
    sub = ap.add_subparsers(dest="command")

    s = sub.add_parser("serve", help="run the web UI")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8420)
    s.add_argument("--lan", action="store_true",
                   help="serve to phones and tablets on the same network")
    s.add_argument("--reload", action="store_true")
    s.set_defaults(func=cmd_serve)

    u = sub.add_parser("upscale", help="upscale one image or video")
    u.add_argument("input")
    u.add_argument("-o", "--output")
    u.add_argument("-m", "--model", default="fast", choices=sorted(MODELS))
    # Ladder order, not alphabetical: sorted() would list 1080p before 180p.
    # `type` runs before the choices check, so aliases such as "hd" resolve
    # to a canonical key and are accepted here exactly as the API accepts them.
    u.add_argument("-p", "--preset", type=resolve_preset, choices=list(PRESETS),
                   metavar="{" + ",".join(PRESETS) + "}",
                   help="target resolution (180p is the fourth stop, by design)")
    u.add_argument("-s", "--scale", type=float, help="scale factor, e.g. 2 or 3.5")
    u.add_argument("--denoise", type=float, default=0.0)
    u.add_argument("--sharpen", type=float, default=0.0)
    u.add_argument("--quality", type=int, default=95, help="JPEG/WebP quality")
    u.add_argument("--tile", type=int, help="tile size override")
    u.add_argument("-y", "--yes", action="store_true",
                   help="do not prompt before long jobs")
    u.set_defaults(func=cmd_upscale)

    i = sub.add_parser("info", help="show models, providers and paths")
    i.set_defaults(func=cmd_info)

    lic = sub.add_parser("license", help="show the licence and pricing")
    lic.set_defaults(func=cmd_license)

    stt = sub.add_parser("status", help="how much of the free allowance is left")
    stt.set_defaults(func=cmd_status)

    act = sub.add_parser("activate", help="activate a licence key you bought")
    act.add_argument("key")
    act.set_defaults(func=cmd_activate)

    dea = sub.add_parser("deactivate", help="remove the licence from this machine")
    dea.set_defaults(func=cmd_deactivate)

    ver = sub.add_parser("verify", help="read the provenance mark from an image")
    ver.add_argument("file")
    ver.set_defaults(func=cmd_verify)

    d = sub.add_parser("download", help="pre-download model weights")
    d.add_argument("models", nargs="*", choices=sorted(MODELS) + [])
    d.set_defaults(func=cmd_download)

    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if not getattr(args, "command", None):
        ap.print_help()
        return 0
    return int(args.func(args) or 0)
