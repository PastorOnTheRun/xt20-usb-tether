/* Relocated RED NIGHT SCREEN overlay for official Cap12 + USB tether.
 *
 * Written for the X-T20 USB tether project. This file is a standalone port,
 * not FujiMod / x70view / Cap12 source. Same pixel math as the hardware-tested
 * v4 overlay (ABGR, alpha byte kept; live-view matrix override).
 * Linked into Cap12's leftover located-0 space at 0x2C52A00 so it does not
 * overwrite Focal UI / cached-arena. The OSD hook chains through Cap12's
 * existing vglib_output_layer_configure thunk (Focal already owns that site).
 */
#if defined(__arm__)
#pragma GCC target("general-regs-only")
#endif

enum { NIGHT_OFF = 0, NIGHT_RED = 1, NIGHT_RED_DIM = 2, NIGHT_MODES = 3 };
enum { LAYOUT_ABGR = 0, LAYOUT_BGRA = 1 };

volatile int red_night_mode = NIGHT_OFF;
volatile unsigned int red_night_osd_passes;
volatile unsigned int red_night_live_words;
volatile int red_night_layout = LAYOUT_ABGR;
volatile int red_night_loaded;
static int last_applied = -1;

static unsigned int level_q8(void)
{
    return red_night_mode == NIGHT_RED_DIM ? 128u : 256u;
}
static unsigned int max3(unsigned int a, unsigned int b, unsigned int c)
{
    unsigned int m = a > b ? a : b;
    return m > c ? m : c;
}
static void recolor_abgr(volatile unsigned int *pixels, unsigned int count, unsigned int q8)
{
    unsigned int i;
    for (i = 0; i < count; ++i) {
        unsigned int w = pixels[i], a = w & 0xffu, m, out;
        if (!a) continue;
        m = (max3(w >> 24, (w >> 16) & 0xffu, (w >> 8) & 0xffu) * q8) >> 8;
        out = (m << 24) | a;
        if (out != w) pixels[i] = out;
    }
}
static void recolor_bgra(volatile unsigned int *pixels, unsigned int count, unsigned int q8)
{
    unsigned int i;
    for (i = 0; i < count; ++i) {
        unsigned int w = pixels[i], a = w & 0xff000000u, m, out;
        if (!a) continue;
        m = (max3((w >> 16) & 0xffu, (w >> 8) & 0xffu, w & 0xffu) * q8) >> 8;
        out = a | (m << 16);
        if (out != w) pixels[i] = out;
    }
}

int red_night_osd_hook(unsigned int *args)
{
    const unsigned short *size = (const unsigned short *)args[1];
    unsigned int buffer = args[2], width, height, count;
    if (red_night_mode <= NIGHT_OFF || red_night_mode >= NIGHT_MODES) return 0;
    if (!size || !buffer || (buffer & 3u)) return 0;
    width = size[0]; height = size[1];
    if (!width || !height || width > 1920u || height > 1080u) return 0;
    count = width * height;
    if (red_night_layout == LAYOUT_BGRA)
        recolor_bgra((volatile unsigned int *)buffer, count, level_q8());
    else
        recolor_abgr((volatile unsigned int *)buffer, count, level_q8());
    red_night_osd_passes++;
    return 0; /* then chain to Cap12's thunk */
}

#define MATRIX_FIRST 0xfff47300u
#define MATRIX_LAST  0xfff47314u
static unsigned int s13(int v) { return (unsigned int)v & 0x1fffu; }
int live_active(void)
{
    return red_night_mode > NIGHT_OFF && red_night_mode < NIGHT_MODES;
}
unsigned int live_word(unsigned int address, unsigned int stock)
{
    int k = red_night_mode == NIGHT_RED_DIM ? 1 : 2;
    int c0 = 306 * k / 2, c1 = 601 * k / 2, c2 = 117 * k / 2;
    if (!live_active() || address < MATRIX_FIRST || address > MATRIX_LAST || (address & 3u))
        return stock;
    red_night_live_words++;
    switch (address - MATRIX_FIRST) {
    case 0x0: return (stock & ~0x1fff1fffu) | s13(c0) | (s13(c1) << 16);
    case 0x4: return (stock & ~0x00001fffu) | s13(c2);
    case 0x8: case 0x10: return stock & ~0x1fff1fffu;
    default: return stock & ~0x00001fffu;
    }
}

/* ---- settings encode/decode without Cap12 json symbols ---- */
static const char *const names[NIGHT_MODES] = {"off", "red", "red_dim"};
static int streq(const char *a, const char *b)
{
    while (*a && *a == *b) { a++; b++; }
    return *a == *b;
}
static int decode(const char *text, int length)
{
    /* Accept {"mode":"red"} / "red_dim" / "off", whitespace-tolerant. */
    int i, n;
    red_night_mode = NIGHT_OFF;
    if (!text || length <= 0) return 1;
    for (i = 0; i < length - 5; i++) {
        if (text[i] == '"' && i + 6 < length && text[i+1]=='m' && text[i+2]=='o'
            && text[i+3]=='d' && text[i+4]=='e' && text[i+5]=='"') {
            int j = i + 6;
            while (j < length && text[j] != '"') j++;
            if (j >= length) break;
            j++;
            for (n = 0; n < NIGHT_MODES; n++) {
                const char *nm = names[n];
                int k, ok = 1;
                for (k = 0; nm[k]; k++)
                    if (j + k >= length || text[j + k] != nm[k]) { ok = 0; break; }
                if (ok && (j + k >= length || text[j + k] == '"')) {
                    red_night_mode = n;
                    return 1;
                }
            }
        }
    }
    return 1;
}

struct x70_json_writer {
    char *out;
    int capacity, length, error;
    int pretty, depth, quoted, escaped, pending;
};
static int encode(struct x70_json_writer *w)
{
    const char *nm = names[(red_night_mode >= 0 && red_night_mode < NIGHT_MODES) ? red_night_mode : 0];
    const char *prefix = "{\"mode\":\"";
    const char *p;
    if (!w) return -28;
    for (p = prefix; *p; p++) {
        if (w->length >= w->capacity) { w->error = -28; return -28; }
        w->out[w->length++] = *p;
    }
    for (p = nm; *p; p++) {
        if (w->length >= w->capacity) { w->error = -28; return -28; }
        w->out[w->length++] = *p;
    }
    if (w->length + 2 > w->capacity) { w->error = -28; return -28; }
    w->out[w->length++] = '"';
    w->out[w->length++] = '}';
    return w->error ? -28 : 0;
}

/* struct x70_settings_file — keep in sync with x70_settings.h (0xf4 in v4). */
struct x70_settings_io { unsigned int pad[12]; }; /* oversized; start() uses the object as a blob */
struct x70_settings_file {
    const char *section;
    const char *filename;
    int (*decode)(const char *, int);
    int (*encode)(struct x70_json_writer *);
    char *buffer; int buffer_size;
    void (*applied)(int);
    int (*ready)(void);
    unsigned char io[60]; /* 15 ints, official x70_settings_io */
    unsigned int requested, completed, failed;
    int registered;
    int error_offset; char error_key[128];
    unsigned int document_index;
};
static char settings_buffer[48];
static void applied(int used);
struct x70_settings_file red_night_settings = {
    "red_night", "SETTINGS.JSN", decode, encode, settings_buffer, 48, applied, 0,
    {0}, 0, 0, 0, 0, 0, {0}, 0
};

typedef void (*disp_osd_fn)(void);
typedef int (*settings_start_fn)(struct x70_settings_file *, int);
void disp_osd_present_request(void);
int x70_settings_start(struct x70_settings_file *, int);

static void refresh_view(void)
{
    disp_osd_present_request();
}
static void applied(int used)
{
    int mode = red_night_mode;
    (void)used;
    if (mode < 0 || mode >= NIGHT_MODES) mode = NIGHT_OFF;
    red_night_loaded = 1;
    if (last_applied < 0 && mode == NIGHT_OFF) {
        last_applied = NIGHT_OFF;
        return;
    }
    last_applied = mode;
    refresh_view();
}
static void changed(int value)
{
    (void)value;
    refresh_view();
}

/* live override registration — layout from film_live_override.h */
struct film_live_override {
    unsigned int priority;
    int (*active)(void);
    unsigned int (*word)(unsigned int, unsigned int);
    void (*observe)(unsigned int, unsigned int);
    int (*dynamic_range)(int, int *);
    int (*exposure_compensation)(int, int, int *);
    const void *(*snapshot)(unsigned int);
    unsigned int (*snapshot_word)(const void *, unsigned int, unsigned int);
};
struct film_live_override_state {
    const struct film_live_override *policy;
    struct film_live_override_state *next;
};
int film_register_live_override(const struct film_live_override *policy,
                                struct film_live_override_state *state);

static struct film_live_override_state live_state;
static const struct film_live_override live_policy = {
    .priority = 40, .active = live_active, .word = live_word
};

struct x70_setting_choice { const char *name; int value; };
static const struct x70_setting_choice choices[] = {
    {"off", NIGHT_OFF}, {"red", NIGHT_RED}, {"red_dim", NIGHT_RED_DIM}, {0, 0}
};
static const char *const labels[] = {"OFF", "RED", "RED DIM"};

/* 0x94-byte XPP menu item, same prefix as v4's red_night_item. */
struct red_menu_item {
    const void *parent;
    unsigned int key;
    const char *label;
    struct x70_settings_file *file;
    volatile int *value;
    const struct x70_setting_choice *choices;
    const char *const *choice_labels;
    void (*changed)(int);
    unsigned char pad[0x94 - 32];
};
extern const void xpp_menu_screen_node;
const struct red_menu_item red_night_item = {
    .parent = &xpp_menu_screen_node,
    .key = 0x140,
    .label = "RED NIGHT SCREEN",
    .file = &red_night_settings,
    .value = &red_night_mode,
    .choices = choices,
    .choice_labels = labels,
    .changed = changed,
};

/* BootSettings subscriber (16 bytes). */
struct fm_subscriber {
    void (*handler)(void);
    unsigned int *counters;
    const char *name;
    unsigned int phase;
};
unsigned int red_night_boot_counters;
void red_night_initialize(void)
{
    (void)film_register_live_override(&live_policy, &live_state);
    (void)x70_settings_start(&red_night_settings, 300);
}
const struct fm_subscriber red_night_boot_sub = {
    red_night_initialize, &red_night_boot_counters,
    "FM_BootSettings red_night_initialize", 1
};
