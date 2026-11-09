import os
import sys
import glob
import requests
import numpy as np

from io import BytesIO
from urllib.parse import urlparse, unquote

from PIL import (
    Image,
    ImageDraw,
    ImageFont,
    ImageEnhance,
    ImageOps,
    ImageFilter,
    ImageStat,
)


# =========================================================
# CONFIG
# =========================================================

DISPLAY_W = 250
DISPLAY_H = 122

COVER_SIZE = 96


MODES = [
    "LEGACY",
    "NORMAL",
    "DETAIL",
    "HIGH_CONTRAST",
    "ATKINSON",
    "THRESHOLD",
]


# Pokud jsou výsledky blíž než 0.8 bodu,
# považujeme je prakticky za remízu.
TIE_THRESHOLD = 0.15


# Při remíze preferujeme bezpečnější algoritmy.
SAFE_PRIORITY = [
    "LEGACY",
    "NORMAL",
    "ATKINSON",
    "DETAIL",
    "HIGH_CONTRAST",
    "THRESHOLD",
]


# =========================================================
# CLEANUP
# =========================================================

def cleanup_old_files():

    patterns = [
        "output_*",
        "compare_*",
    ]

    for pattern in patterns:

        for file in glob.glob(pattern):

            try:
                os.remove(file)

            except OSError:
                pass


# =========================================================
# INPUT
# =========================================================

def is_url(value):

    value = value.strip().lower()

    return (
        value.startswith("http://")
        or value.startswith("https://")
    )


def derive_caption(source):

    if is_url(source):

        path = urlparse(source).path

        name = os.path.basename(path)

        name = unquote(name)

    else:

        name = os.path.basename(source)


    stem, _ = os.path.splitext(name)

    stem = (
        stem
        .replace("_", " ")
        .replace("-", " ")
        .strip()
    )

    if not stem:
        return "IMAGE"

    return stem[:18]


def load_image(source):

    if is_url(source):

        print(
            f"\nStahuji obrázek z URL:\n{source}"
        )

        response = requests.get(
            source,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=(5, 20)
        )

        response.raise_for_status()

        return Image.open(
            BytesIO(response.content)
        ).convert("RGB")


    print(
        f"\nNačítám lokální soubor:\n{source}"
    )

    return Image.open(
        source
    ).convert("RGB")


# =========================================================
# FONT
# =========================================================

def get_font(size):

    paths = [

        "/System/Library/Fonts/Supplemental/Arial.ttf",

        "/System/Library/Fonts/Supplemental/Helvetica.ttc",

        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",

    ]


    for path in paths:

        try:

            return ImageFont.truetype(
                path,
                size
            )

        except OSError:
            pass


    return ImageFont.load_default()


# =========================================================
# BASE COVER
# =========================================================

def prepare_base_cover(image):

    image = ImageOps.fit(
        image,
        (
            COVER_SIZE,
            COVER_SIZE
        ),
        method=Image.Resampling.LANCZOS
    )

    return image.convert("L")


def image_metrics(gray_image):

    stat = ImageStat.Stat(
        gray_image
    )

    contrast_std = stat.stddev[0]

    brightness_mean = stat.mean[0]


    edges = gray_image.filter(
        ImageFilter.FIND_EDGES
    )

    edge_stat = ImageStat.Stat(
        edges
    )

    edge_mean = edge_stat.mean[0]


    return {

        "contrast_std":
            contrast_std,

        "brightness_mean":
            brightness_mean,

        "edge_mean":
            edge_mean,

    }


def print_metrics(gray_image):

    metrics = image_metrics(
        gray_image
    )

    print("\nAnalýza coveru:")

    print(
        f"  contrast_std    : "
        f"{metrics['contrast_std']:.2f}"
    )

    print(
        f"  brightness_mean : "
        f"{metrics['brightness_mean']:.2f}"
    )

    print(
        f"  edge_mean       : "
        f"{metrics['edge_mean']:.2f}"
    )


# =========================================================
# DITHERING
# =========================================================

def floyd_dither(image_l):

    return image_l.convert(
        "1",
        dither=Image.Dither.FLOYDSTEINBERG
    )


def threshold_dither(
    image_l,
    threshold=128
):

    return image_l.point(
        lambda p:
            255 if p > threshold else 0,
        mode="1"
    )


def atkinson_dither(image_l):

    img = image_l.copy().convert("L")

    pixels = img.load()

    width, height = img.size


    for y in range(height):

        for x in range(width):

            old = pixels[x, y]

            new = (
                255
                if old > 127
                else 0
            )

            pixels[x, y] = new


            error = (
                old - new
            ) / 8.0


            neighbors = [

                (1, 0),

                (2, 0),

                (-1, 1),

                (0, 1),

                (1, 1),

                (0, 2),

            ]


            for dx, dy in neighbors:

                nx = x + dx

                ny = y + dy


                if (
                    0 <= nx < width
                    and
                    0 <= ny < height
                ):

                    value = (
                        pixels[nx, ny]
                        + error
                    )

                    value = max(
                        0,
                        min(
                            255,
                            int(value)
                        )
                    )

                    pixels[nx, ny] = value


    return img.convert("1")


# =========================================================
# PROCESSING MODES
# =========================================================

def preprocess_legacy(gray):

    img = ImageOps.autocontrast(
        gray,
        cutoff=1
    )

    img = img.filter(
        ImageFilter.UnsharpMask(
            radius=1,
            percent=150,
            threshold=2
        )
    )

    img = ImageEnhance.Contrast(
        img
    ).enhance(1.15)

    return floyd_dither(img)


def preprocess_normal(gray):

    img = ImageOps.autocontrast(
        gray,
        cutoff=1
    )

    img = img.filter(
        ImageFilter.UnsharpMask(
            radius=1,
            percent=140,
            threshold=2
        )
    )

    img = ImageEnhance.Contrast(
        img
    ).enhance(1.15)

    return floyd_dither(img)


def preprocess_detail(gray):

    img = ImageOps.autocontrast(
        gray,
        cutoff=0
    )

    img = img.filter(
        ImageFilter.DETAIL
    )

    img = img.filter(
        ImageFilter.UnsharpMask(
            radius=1,
            percent=170,
            threshold=1
        )
    )

    img = ImageEnhance.Contrast(
        img
    ).enhance(1.25)

    img = ImageEnhance.Sharpness(
        img
    ).enhance(1.15)

    return floyd_dither(img)


def preprocess_high_contrast(gray):

    img = ImageOps.autocontrast(
        gray,
        cutoff=2
    )

    img = img.filter(
        ImageFilter.UnsharpMask(
            radius=1,
            percent=180,
            threshold=1
        )
    )

    img = ImageEnhance.Contrast(
        img
    ).enhance(1.45)

    img = ImageEnhance.Sharpness(
        img
    ).enhance(1.20)


    img = img.point(

        lambda p: max(

            0,

            min(

                255,

                int(
                    (p - 128)
                    * 1.20
                    + 128
                )

            )

        )

    )


    return atkinson_dither(img)


def preprocess_atkinson(gray):

    img = ImageOps.autocontrast(
        gray,
        cutoff=1
    )

    img = img.filter(
        ImageFilter.UnsharpMask(
            radius=1,
            percent=150,
            threshold=1
        )
    )

    img = ImageEnhance.Contrast(
        img
    ).enhance(1.20)

    return atkinson_dither(img)


def preprocess_threshold(gray):

    img = ImageOps.autocontrast(
        gray,
        cutoff=1
    )

    img = img.filter(
        ImageFilter.UnsharpMask(
            radius=1,
            percent=170,
            threshold=1
        )
    )

    img = ImageEnhance.Contrast(
        img
    ).enhance(1.35)


    return threshold_dither(
        img,
        threshold=128
    )


def process_cover(
    base_gray,
    mode
):

    if mode == "LEGACY":

        return preprocess_legacy(
            base_gray
        )


    if mode == "NORMAL":

        return preprocess_normal(
            base_gray
        )


    if mode == "DETAIL":

        return preprocess_detail(
            base_gray
        )


    if mode == "HIGH_CONTRAST":

        return preprocess_high_contrast(
            base_gray
        )


    if mode == "ATKINSON":

        return preprocess_atkinson(
            base_gray
        )


    if mode == "THRESHOLD":

        return preprocess_threshold(
            base_gray
        )


    raise ValueError(
        f"Neplatný režim: {mode}"
    )


# =========================================================
# PERCEPTUAL SCORE
# =========================================================

def image_to_array(image):

    return np.asarray(
        image.convert("L"),
        dtype=np.float32
    ) / 255.0


def safe_correlation(
    a,
    b
):

    a = a.flatten()

    b = b.flatten()


    a_std = np.std(a)

    b_std = np.std(b)


    if (
        a_std < 1e-6
        or
        b_std < 1e-6
    ):

        return 0.0


    corr = np.corrcoef(
        a,
        b
    )[0, 1]


    if np.isnan(corr):

        return 0.0


    return float(

        max(
            0.0,
            min(
                1.0,
                corr
            )
        )

    )


# ---------------------------------------------------------
# RECONSTRUCTION
# ---------------------------------------------------------

def reconstruction_score(
    original,
    candidate
):

    sizes = [

        (48, 48, 0.45),

        (24, 24, 0.35),

        (12, 12, 0.20),

    ]


    total = 0.0


    for width, height, weight in sizes:

        orig_small = original.resize(
            (
                width,
                height
            ),
            Image.Resampling.BOX
        )


        cand_small = candidate.resize(
            (
                width,
                height
            ),
            Image.Resampling.BOX
        )


        orig_arr = image_to_array(
            orig_small
        )


        cand_arr = image_to_array(
            cand_small
        )


        mae = np.mean(

            np.abs(

                orig_arr
                -
                cand_arr

            )

        )


        score = (
            1.0
            -
            mae
        )


        total += (
            score
            *
            weight
        )


    return float(total)


# ---------------------------------------------------------
# STRUCTURE
# ---------------------------------------------------------

def structure_score(
    original,
    candidate
):

    orig_blur = original.filter(

        ImageFilter.GaussianBlur(
            radius=1.4
        )

    )


    cand_blur = candidate.convert(
        "L"
    ).filter(

        ImageFilter.GaussianBlur(
            radius=1.4
        )

    )


    return safe_correlation(

        image_to_array(
            orig_blur
        ),

        image_to_array(
            cand_blur
        )

    )


# ---------------------------------------------------------
# GRADIENT / EDGES
# ---------------------------------------------------------

def gradient_score(
    original,
    candidate
):

    orig = original.filter(

        ImageFilter.GaussianBlur(
            radius=1.0
        )

    )


    cand = candidate.convert(
        "L"
    ).filter(

        ImageFilter.GaussianBlur(
            radius=1.0
        )

    )


    orig_arr = image_to_array(
        orig
    )


    cand_arr = image_to_array(
        cand
    )


    orig_gy, orig_gx = np.gradient(
        orig_arr
    )


    cand_gy, cand_gx = np.gradient(
        cand_arr
    )


    orig_vector = np.concatenate(

        [
            orig_gx.flatten(),
            orig_gy.flatten(),
        ]

    )


    cand_vector = np.concatenate(

        [
            cand_gx.flatten(),
            cand_gy.flatten(),
        ]

    )


    denominator = (

        np.linalg.norm(
            orig_vector
        )

        *

        np.linalg.norm(
            cand_vector
        )

    )


    if denominator < 1e-8:

        return 0.0


    similarity = (

        np.dot(
            orig_vector,
            cand_vector
        )

        /

        denominator

    )


    similarity = (

        similarity
        +
        1.0

    ) / 2.0


    return float(

        max(
            0.0,
            min(
                1.0,
                similarity
            )
        )

    )


# ---------------------------------------------------------
# LOCAL CONTRAST
# ---------------------------------------------------------

def local_contrast_score(
    original,
    candidate
):

    orig = original.filter(

        ImageFilter.GaussianBlur(
            radius=0.8
        )

    )


    cand = candidate.convert(
        "L"
    ).filter(

        ImageFilter.GaussianBlur(
            radius=0.8
        )

    )


    orig_arr = image_to_array(
        orig
    )


    cand_arr = image_to_array(
        cand
    )


    tile = 12


    orig_contrasts = []

    cand_contrasts = []


    for y in range(
        0,
        COVER_SIZE,
        tile
    ):

        for x in range(
            0,
            COVER_SIZE,
            tile
        ):


            orig_block = orig_arr[
                y:y + tile,
                x:x + tile
            ]


            cand_block = cand_arr[
                y:y + tile,
                x:x + tile
            ]


            if orig_block.size == 0:

                continue


            orig_contrasts.append(
                np.std(
                    orig_block
                )
            )


            cand_contrasts.append(
                np.std(
                    cand_block
                )
            )


    if not orig_contrasts:

        return 0.0


    orig_contrasts = np.array(
        orig_contrasts
    )


    cand_contrasts = np.array(
        cand_contrasts
    )


    difference = np.mean(

        np.abs(

            orig_contrasts
            -
            cand_contrasts

        )

    )


    return float(

        1.0
        -
        min(
            1.0,
            difference / 0.30
        )

    )


# ---------------------------------------------------------
# MIDTONE PENALTY
# ---------------------------------------------------------

def midtone_preservation_penalty(
    original,
    candidate
):

    original_arr = image_to_array(
        original
    )


    candidate_arr = image_to_array(
        candidate
    )


    tile = 8


    evaluated = 0

    bad = 0


    for y in range(
        0,
        COVER_SIZE,
        tile
    ):

        for x in range(
            0,
            COVER_SIZE,
            tile
        ):


            orig_block = original_arr[
                y:y + tile,
                x:x + tile
            ]


            cand_block = candidate_arr[
                y:y + tile,
                x:x + tile
            ]


            if orig_block.size == 0:

                continue


            orig_mean = np.mean(
                orig_block
            )


            orig_std = np.std(
                orig_block
            )


            if (

                0.15 < orig_mean < 0.85

                and

                orig_std > 0.04

            ):


                evaluated += 1


                cand_mean = np.mean(
                    cand_block
                )


                if (

                    cand_mean < 0.04

                    or

                    cand_mean > 0.96

                ):

                    bad += 1


    if evaluated == 0:

        return 1.0


    bad_ratio = (

        bad
        /
        evaluated

    )


    penalty = (

        1.0
        -
        bad_ratio * 0.40

    )


    return float(

        max(
            0.60,
            penalty
        )

    )


# ---------------------------------------------------------
# GLOBAL BALANCE
# ---------------------------------------------------------

def global_balance_penalty(
    original,
    candidate
):

    orig_arr = image_to_array(
        original
    )


    cand_arr = image_to_array(
        candidate
    )


    original_darkness = (

        1.0
        -
        np.mean(
            orig_arr
        )

    )


    candidate_darkness = (

        1.0
        -
        np.mean(
            cand_arr
        )

    )


    difference = abs(

        original_darkness
        -
        candidate_darkness

    )


    if difference < 0.05:

        return 1.0


    if difference < 0.10:

        return 0.97


    if difference < 0.18:

        return 0.90


    return 0.80


# ---------------------------------------------------------
# FINAL SCORE
# ---------------------------------------------------------

def score_variant(
    original_gray,
    candidate,
    return_details=False
):

    original = original_gray.convert(
        "L"
    )


    candidate_l = candidate.convert(
        "L"
    )


    reconstruction = reconstruction_score(
        original,
        candidate_l
    )


    structure = structure_score(
        original,
        candidate_l
    )


    gradient = gradient_score(
        original,
        candidate_l
    )


    contrast = local_contrast_score(
        original,
        candidate_l
    )


    midtone_penalty = (

        midtone_preservation_penalty(
            original,
            candidate_l
        )

    )


    balance_penalty = (

        global_balance_penalty(
            original,
            candidate_l
        )

    )


    raw_score = (

        reconstruction * 0.45

        +

        structure * 0.25

        +

        gradient * 0.20

        +

        contrast * 0.10

    )


    final_score = (

        raw_score

        *

        midtone_penalty

        *

        balance_penalty

    )


    final_score *= 100.0


    details = {

        "reconstruction":
            reconstruction * 100,

        "structure":
            structure * 100,

        "gradient":
            gradient * 100,

        "contrast":
            contrast * 100,

        "midtone_penalty":
            midtone_penalty,

        "balance_penalty":
            balance_penalty,

    }


    if return_details:

        return (
            float(final_score),
            details
        )


    return float(
        final_score
    )


# =========================================================
# CONFIDENCE-AWARE WINNER
# =========================================================

def choose_best_mode(scores):

    sorted_modes = sorted(

        scores,

        key=scores.get,

        reverse=True

    )


    top_mode = sorted_modes[0]

    top_score = scores[
        top_mode
    ]


    second_mode = sorted_modes[1]

    second_score = scores[
        second_mode
    ]


    margin = (

        top_score
        -
        second_score

    )


    tied_modes = [

        mode

        for mode in sorted_modes

        if (

            top_score
            -
            scores[mode]

        ) <= TIE_THRESHOLD

    ]


    # jasný vítěz
    if len(tied_modes) == 1:

        return (

            top_mode,

            "CLEAR WINNER",

            margin,

            tied_modes

        )


    # remíza
    best_mode = next(

        mode

        for mode in SAFE_PRIORITY

        if mode in tied_modes

    )


    reason = (

        "TIE / LOW CONFIDENCE: "

        +

        ", ".join(
            tied_modes
        )

    )


    return (

        best_mode,

        reason,

        margin,

        tied_modes

    )


# =========================================================
# DISPLAY MOCKUP
# =========================================================

def create_display_mockup(
    image_1bit,
    caption,
    mode_used
):

    display = Image.new(
        "1",
        (
            DISPLAY_W,
            DISPLAY_H
        ),
        1
    )


    display.paste(
        image_1bit,
        (4, 13)
    )


    draw = ImageDraw.Draw(
        display
    )


    title_font = get_font(14)

    small_font = get_font(9)


    x = 106


    draw.text(
        (x, 14),
        caption[:16],
        font=title_font,
        fill=0
    )


    # play
    draw.rectangle(
        (
            x,
            48,
            x + 12,
            60
        ),
        outline=0,
        fill=1
    )


    draw.polygon(
        [
            (x + 3, 51),
            (x + 3, 57),
            (x + 9, 54),
        ],
        fill=0
    )


    # progress
    bar_x = x + 18

    bar_y = 53

    bar_w = 110


    draw.rectangle(
        (
            bar_x,
            bar_y,
            bar_x + bar_w,
            bar_y + 3
        ),
        fill=0
    )


    progress = 0.62


    draw.rectangle(
        (
            bar_x
            +
            int(
                bar_w
                *
                progress
            ),

            bar_y - 1,

            bar_x + bar_w,

            bar_y + 4,
        ),
        fill=1
    )


    draw.text(
        (x, 82),
        "250x122 E-INK",
        font=small_font,
        fill=0
    )


    draw.text(
        (x, 95),
        f"MODE: {mode_used}",
        font=small_font,
        fill=0
    )


    return display


# =========================================================
# COVER COMPARISON
# =========================================================

def create_cover_comparison(
    variants,
    caption,
    scores,
    best_mode
):

    cols = len(
        variants
    )


    label_h = 30

    gap = 8

    margin = 8


    canvas_w = (

        margin * 2

        +

        cols * COVER_SIZE

        +

        (cols - 1) * gap

    )


    canvas_h = (

        margin * 2

        +

        label_h

        +

        COVER_SIZE

        +

        8

    )


    img = Image.new(
        "1",
        (
            canvas_w,
            canvas_h
        ),
        1
    )


    draw = ImageDraw.Draw(
        img
    )


    title_font = get_font(12)

    small_font = get_font(8)


    draw.text(
        (margin, 2),
        f"Cover comparison: {caption}",
        font=title_font,
        fill=0
    )


    x = margin

    y = (
        margin
        +
        label_h
    )


    for mode_name, cover_img in variants.items():


        label = (

            f"{mode_name} "

            f"{scores[mode_name]:.1f}"

        )


        if mode_name == best_mode:

            label += " *"


        bbox = draw.textbbox(
            (0, 0),
            label,
            font=small_font
        )


        label_w = (

            bbox[2]
            -
            bbox[0]

        )


        label_x = (

            x

            +

            max(

                0,

                (
                    COVER_SIZE
                    -
                    label_w
                ) / 2

            )

        )


        draw.text(
            (
                label_x,
                y - 14
            ),
            label,
            font=small_font,
            fill=0
        )


        img.paste(
            cover_img,
            (x, y)
        )


        x += (

            COVER_SIZE
            +
            gap

        )


    return img


# =========================================================
# MAIN
# =========================================================

def main():

    cleanup_old_files()


    # -----------------------------------------------------
    # SOURCE
    # -----------------------------------------------------

    if len(sys.argv) > 1:

        source = (
            sys.argv[1]
            .strip()
        )

    else:

        source = input(
            "Vlož URL nebo cestu k obrázku: "
        ).strip()


    if not source:

        print(
            "Nebyl zadán žádný obrázek."
        )

        return


    default_caption = derive_caption(
        source
    )


    if len(sys.argv) > 2:

        caption = (
            sys.argv[2]
            .strip()
        )

    else:

        caption = input(

            f"Popisek "
            f"(Enter = {default_caption}): "

        ).strip()


        if not caption:

            caption = default_caption


    # -----------------------------------------------------
    # LOAD
    # -----------------------------------------------------

    try:

        original = load_image(
            source
        )


    except Exception as e:

        print(
            "\nChyba při načítání obrázku:"
        )

        print(e)

        return


    original.save(
        "output_original.jpg",
        quality=95
    )


    base_gray = prepare_base_cover(
        original
    )


    print_metrics(
        base_gray
    )


    cover_variants = {}

    display_variants = {}


    # -----------------------------------------------------
    # GENERATE
    # -----------------------------------------------------

    for mode in MODES:


        print(
            f"\nGeneruji režim: {mode}"
        )


        eink_img = process_cover(
            base_gray,
            mode
        )


        cover_variants[
            mode
        ] = eink_img


        eink_img.save(

            f"output_cover_"
            f"{mode.lower()}.png"

        )


        display_img = create_display_mockup(
            eink_img,
            caption,
            mode
        )


        display_variants[
            mode
        ] = display_img


        display_img.save(

            f"output_display_"
            f"{mode.lower()}.png"

        )


    # -----------------------------------------------------
    # SCORE
    # -----------------------------------------------------

    scores = {}

    details = {}


    print()

    print("=" * 62)

    print(
        "PERCEPTUAL AUTO SCORE V2"
    )

    print("=" * 62)


    for mode, cover in cover_variants.items():


        score, info = score_variant(

            base_gray,

            cover,

            return_details=True

        )


        scores[
            mode
        ] = score


        details[
            mode
        ] = info


    (
        best_mode,
        selection_reason,
        margin,
        tied_modes

    ) = choose_best_mode(
        scores
    )


    print()


    for mode in MODES:


        marker = ""


        if mode == best_mode:

            marker = "  <-- SELECTED"


        d = details[
            mode
        ]


        print(

            f"{mode:16}"

            f"{scores[mode]:7.2f}"

            f"{marker}"

        )


        print(

            f"   tone {d['reconstruction']:5.1f}"

            f" | structure {d['structure']:5.1f}"

            f" | edges {d['gradient']:5.1f}"

            f" | detail {d['contrast']:5.1f}"

        )


    print()

    print(
        f"Top score margin: "
        f"{margin:.2f}"
    )


    print(
        f"Selection: "
        f"{selection_reason}"
    )


    # -----------------------------------------------------
    # BEST
    # -----------------------------------------------------

    best_cover = cover_variants[
        best_mode
    ]


    best_cover.save(
        "output_best.png"
    )


    best_display = display_variants[
        best_mode
    ]


    best_display.save(
        "output_best_display.png"
    )


    best_preview = best_display.resize(

        (
            DISPLAY_W * 5,
            DISPLAY_H * 5
        ),

        Image.Resampling.NEAREST

    )


    best_preview.save(
        "output_best_preview.png"
    )


    # -----------------------------------------------------
    # COMPARISON
    # -----------------------------------------------------

    comparison = create_cover_comparison(

        cover_variants,

        caption,

        scores,

        best_mode

    )


    comparison.save(
        "compare_covers.png"
    )


    preview = comparison.resize(

        (
            comparison.width * 2,
            comparison.height * 2
        ),

        Image.Resampling.NEAREST

    )


    preview.save(
        "compare_covers_preview.png"
    )


    # -----------------------------------------------------
    # DONE
    # -----------------------------------------------------

    print()

    print("=" * 62)

    print(
        f"VÍTĚZ: {best_mode}"
    )

    print("=" * 62)


    print(
        "\nVýsledek:"
    )

    print(
        "  output_best.png"
    )

    print(
        "  output_best_display.png"
    )

    print(
        "  output_best_preview.png"
    )


    print(
        "\nPorovnání:"
    )

    print(
        "  compare_covers.png"
    )

    print(
        "  compare_covers_preview.png"
    )


    print(
        "\nNa Macu:"
    )

    print(
        "  open compare_covers_preview.png"
    )

    print(
        "  open output_best_preview.png"
    )


if __name__ == "__main__":

    main()