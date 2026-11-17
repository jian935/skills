# -*- coding: utf-8 -*-
"""六个主题的提示词。风格锚段全系列复用，保证六张是同一套画风。"""

# ---------------- 画风锚（伪厚涂）----------------
STYLE = ("pseudo-impasto illustration, semi-realistic anime painting, soft thick impasto brushwork "
         "blended into delicate gradients, clean crisp lineart edges kept visible, "
         "warm golden autumn sunlight, glowing backlight, rim light, "
         "volumetric light rays, atmospheric haze, floating dust motes, lens flare, bokeh, "
         "healing and cozy atmosphere, clean composition with negative space, "
         "palette of warm orange, caramel, cream yellow and deep brown, "
         "highly detailed, masterpiece, best quality, official art, "
         "vertical composition")

NEG = ("worst quality, low quality, lowres, blurry, jpeg artifacts, "
       "watermark, signature, username, text, logo, web address, "
       "bad anatomy, bad proportions, bad hands, extra fingers, fewer fingers, "
       "fused fingers, deformed hands, extra limbs, extra arms, extra legs, "
       "deformed face, distorted face, mutated, ugly, "
       "monochrome, greyscale, sketch, lineart, uncolored, "
       "flat color, cel shading, flat shading, oversaturated, neon colors, "
       "muddy colors, dirty colors, greyed out, 3d, cgi, photorealistic")

# 暗调场景（第 2、6 题）额外压制过曝
NEG_DARK = (NEG + ", blown out highlights, overexposed, daylight, "
            "bright noon light, washed out")

# ---------------- 六主题 ----------------
THEMES = [
    dict(
        key="t1", no=1, name="秋日放学路",
        scene=("1girl, little girl, child, twin tails, brown hair, from behind, "
               "walking away down a tree-lined path covered with fallen ginkgo leaves, "
               "wearing a canvas school backpack, holding one fallen ginkgo leaf up "
               "toward the setting sun, looking at the leaf, "
               "golden hour sunlight slanting through the gaps between tall ginkgo trees, "
               "strong backlight rim lighting her hair, very long shadow stretching on the path, "
               "a wooden bench in the distance with a father sitting and waving at her, "
               "floating leaves in the air, autumn ginkgo avenue, warm orange sunset glow"),
        neg_list="child, loli, young child, adult, mature female, 2girls, multiple girls",
    ),
    dict(
        key="t2", no=2, name="秋雨窗边读信",
        scene=("1boy, young man, short brown hair, wearing a cream white knit cardigan, "
               "sitting by an old wooden window, holding a yellowed old letter in both hands, "
               "reading it with a gentle smile, "
               "rainy autumn afternoon outside the window, red maple leaves outside, "
               "raindrops on the window glass refracting soft light, "
               "a warm yellow table lamp on the desk beside him, "
               "a steaming cup of coffee, an open sketchbook and a few pine cones on the windowsill, "
               "warm yellow lamp light against the cool grey blue rainy day, "
               "quiet and peaceful, indoor scene"),
        neg_list="daylight, sunny, bright outdoor light",
    ),
    dict(
        key="t3", no=3, name="枫林晨间散步",
        scene=("1boy and 1girl, young couple, side by side, walking down a maple forest path, "
               "boy wearing a caramel brown long coat, girl wearing a beige knit scarf, "
               "morning wind lifting the hem of their clothes, "
               "turning to look at each other and smiling, "
               "fiery red and golden maple leaves covering the ground, "
               "morning sunlight through the tree canopy, dappled light spots on the ground, "
               "thin mist floating in the distance, "
               "bright warm morning, red maple forest"),
        neg_list="night, dark, gloomy",
    ),
    dict(
        key="t4", no=4, name="黄昏站台归途",
        scene=("1boy, high school student, wearing a school uniform, standing alone on "
               "the platform of a small town train station, "
               "holding a suitcase in one hand, his scarf blown up by the wind, "
               "looking at a train approaching in the distance, calm and gentle expression, "
               "expecting to go home, "
               "a tall ginkgo tree beside the platform with golden leaves falling, "
               "a street lamp just turned on glowing warm, "
               "dusk sky blending warm orange and pale purple at the horizon, "
               "train platform, railway, evening"),
        neg_list="daylight, bright noon, sunny sky",
    ),
    dict(
        key="t5", no=5, name="秋收后的庭院",
        scene=("old man, white beard, elderly man, sitting on a bamboo chair peeling persimmons, "
               "rural farm courtyard in the afternoon, "
               "bamboo baskets full of pumpkins, persimmons and ears of rice beside him, "
               "a calico cat curled up asleep on the stone steps, "
               "strings of golden corn cobs hanging and drying on the wall, "
               "green vines climbing all over the brick wall, "
               "sunlight slanting on the red brick ground, fallen leaves, "
               "harvest warmth, cozy countryside life"),
        neg_list="young man, child, 2boys, crowd",
    ),
    dict(
        key="t6", no=6, name="秋夜天台观星",
        scene=("1girl, little girl, wearing a cream white sweater, wrapped in a blanket, "
               "sitting cross-legged on a rattan chair on a rooftop at night, "
               "looking up at the starry sky, "
               "her older brother standing beside her holding a flashlight, "
               "a small table with a cup of hot cocoa and a warm yellow lamp, "
               "a few ginkgo leaves resting on the railing, "
               "deep blue night sky with soft warm yellow lamplight, "
               "thin clouds drifting, faint milky way and stars, "
               "quiet and romantic, rooftop at night"),
        neg_list="daylight, daytime, bright sky, sun, overexposed",
    ),
]


def full_prompt(t, stage="color"):
    """stage: draft / lineart / color"""
    if stage == "lineart":
        return ("lineart, monochrome line drawing, black ink lines on pure white background, "
                "clean crisp anime lineart, varied line weight, "
                "detailed outlines, no shading, no color, no tone, "
                "manga line art, " + t["scene"])
    if stage == "draft":
        return t["scene"] + ", " + STYLE + ", rough composition study, loose sketch feel"
    return t["scene"] + ", " + STYLE


def neg_prompt(t, stage="color"):
    if stage == "lineart":
        return ("color, colored, color cast, shading, shadow, tone, gradient, "
                "greyscale background, grey background, texture, noise, "
                "blurry lines, messy lines, sketchy, rough, "
                "worst quality, low quality, watermark, signature, text, "
                "bad anatomy, extra limbs, deformed hands")
    base = NEG_DARK if t["key"] in ("t2", "t6") else NEG
    if t["neg_list"]:
        base += ", " + t["neg_list"]
    return base
