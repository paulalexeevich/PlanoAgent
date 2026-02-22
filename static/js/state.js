/* STATE — Global variables, constants, palettes */

let planogramData = null;
let summaryData = null;
let productsMap = {};
let scale = 6; // pixels per inch
let useMetric = false; // false = inches, true = cm
let equipmentGenerated = false; // true after Step 1
let decisionTreeData = null;   // decision tree definition
let complianceData = null;     // compliance report from backend
let currentLayer = 'products'; // 'products' | 'dt-0' | 'dt-1' | ...
let dtPositionMap = {};        // product_id → {LevelName: groupValue, ...}

const DT_KNOWN_PALETTES = {
    'Segment': {
        'Domestic':  '#4a9eff',
        'Craft':     '#f59e0b',
        'Import':    '#34d399',
        'Specialty': '#a78bfa',
        'Other':     '#9aa0a6',
    },
    'Package': {
        'can':         '#4a9eff',
        'bottle':      '#34d399',
        'tallboy_can': '#f59e0b',
        'tallboy':     '#e879f9',
    },
};

const DT_AUTO_COLORS = [
    '#4a9eff', '#f59e0b', '#34d399', '#a78bfa', '#ef4444',
    '#06b6d4', '#f97316', '#84cc16', '#ec4899', '#14b8a6',
    '#8b5cf6', '#facc15', '#fb923c', '#4ade80', '#38bdf8',
];

const SEGMENT_COLORS = {
    'Domestic': '#4a9eff',
    'Craft':    '#f59e0b',
    'Import':   '#34d399',
    'Specialty':'#a78bfa',
    'Other':    '#9aa0a6',
};
