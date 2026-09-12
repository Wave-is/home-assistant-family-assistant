/* Family Assistant control-center layout, using Home Assistant theme tokens. */
export const PANEL_STYLES = `
:host {
  display: block;
  min-height: 100vh;
  background-color: var(--primary-background-color, #f4f6f9);
  color: var(--primary-text-color, #1e293b);
  font-family: var(--paper-font-body1_-_font-family, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif);
  box-sizing: border-box;
  -webkit-font-smoothing: antialiased;
}

*, *:before, *:after {
  box-sizing: inherit;
}

.panel-container {
  max-width: 1440px;
  margin: 0 auto;
  padding: 16px 24px 60px;
}

/* ================= HEADER ================= */
.header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--divider-color, rgba(0,0,0,0.08));
}

.header-brand {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-icon-box {
  width: 50px;
  height: 50px;
  border-radius: 16px;
  background: linear-gradient(135deg, #0288d1 0%, #00b4d8 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 28px;
  box-shadow: 0 4px 14px rgba(2, 136, 209, 0.35);
}

.header-brand h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.4px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-brand p {
  margin: 2px 0 0;
  font-size: 13px;
  color: var(--secondary-text-color, #64748b);
  font-weight: 500;
}

.header-brand .quote {
  font-style: italic;
  color: var(--secondary-text-color, #94a3b8);
  font-size: 12px;
  margin-top: 2px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.header-weather-time {
  display: flex;
  align-items: center;
  gap: 14px;
  background: var(--card-background-color, #ffffff);
  border: 1px solid var(--divider-color, rgba(0,0,0,0.08));
  padding: 8px 16px;
  border-radius: 14px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}

.weather-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--primary-text-color, #1e293b);
}

.time-pill {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  border-left: 1px solid var(--divider-color, rgba(0,0,0,0.1));
  padding-left: 12px;
}

.time-pill .clock {
  font-size: 18px;
  font-weight: 700;
  line-height: 1.1;
  color: var(--primary-text-color, #1e293b);
}

.time-pill .date {
  font-size: 11px;
  color: var(--secondary-text-color, #64748b);
}

/* Search Box */
.search-box {
  position: relative;
  min-width: 260px;
  max-width: 360px;
  flex: 1;
}

.search-box input {
  width: 100%;
  padding: 10px 14px 10px 38px;
  border-radius: 20px;
  border: 1px solid var(--divider-color, rgba(0,0,0,0.12));
  background: var(--card-background-color, #ffffff);
  color: var(--primary-text-color, #1e293b);
  font-size: 14px;
  outline: none;
  transition: all 0.2s ease;
}

.search-box input:focus {
  border-color: var(--primary-color, #0288d1);
  box-shadow: 0 0 0 3px rgba(2, 136, 209, 0.15);
}

.search-box .search-icon {
  position: absolute;
  left: 14px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 15px;
  color: var(--secondary-text-color, #94a3b8);
  pointer-events: none;
}

/* ================= NAV TABS ================= */
.nav-tabs {
  display: flex;
  overflow-x: auto;
  gap: 8px;
  padding-bottom: 2px;
  margin-bottom: 22px;
  border-bottom: 1px solid var(--divider-color, rgba(0,0,0,0.08));
  scrollbar-width: none;
}

.nav-tabs::-webkit-scrollbar {
  display: none;
}

.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border-radius: 12px 12px 0 0;
  border: none;
  background: transparent;
  color: var(--secondary-text-color, #64748b);
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s ease-in-out;
  border-bottom: 3px solid transparent;
  margin-bottom: -1px;
}

.tab-btn:hover {
  color: var(--primary-color, #0288d1);
  background: rgba(2, 136, 209, 0.05);
}

.tab-btn.active {
  color: var(--primary-color, #0288d1);
  font-weight: 700;
  border-bottom-color: var(--primary-color, #0288d1);
  background: rgba(2, 136, 209, 0.08);
}

/* Sub-tabs inside view */
.sub-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--divider-color, rgba(0,0,0,0.08));
  padding-bottom: 4px;
  overflow-x: auto;
}

.sub-tab-btn {
  padding: 8px 16px;
  border-radius: 10px;
  border: none;
  background: transparent;
  font-size: 14px;
  font-weight: 600;
  color: var(--secondary-text-color, #64748b);
  cursor: pointer;
  transition: all 0.15s;
}

.sub-tab-btn:hover {
  background: rgba(0,0,0,0.04);
  color: var(--primary-text-color, #1e293b);
}

.sub-tab-btn.active {
  background: var(--primary-color, #0288d1);
  color: #ffffff;
  box-shadow: 0 2px 6px rgba(2, 136, 209, 0.3);
}

/* ================= CARDS & LAYOUT ================= */
.card {
  background: var(--card-background-color, #ffffff);
  border-radius: 18px;
  padding: 20px;
  box-shadow: var(--ha-card-box-shadow, 0 2px 10px rgba(0,0,0,0.05));
  border: 1px solid var(--divider-color, rgba(0,0,0,0.08));
  transition: transform 0.15s, box-shadow 0.15s;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.card-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
}

.grid {
  display: grid;
  gap: 16px;
}

.grid-cols-4 {
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
}

.grid-cols-3 {
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
}

.grid-cols-2 {
  grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
}

/* ================= FAMILY MEMBERS ROW (Ref 2, 3, 4) ================= */
.family-hero-card {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  background: var(--card-background-color, #ffffff);
  border-radius: 20px;
  padding: 18px 22px;
  border: 1px solid var(--divider-color, rgba(0,0,0,0.08));
  box-shadow: 0 2px 10px rgba(0,0,0,0.04);
}

.members-avatars-row {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.member-avatar-pill {
  display: flex;
  align-items: center;
  gap: 12px;
  background: rgba(0,0,0,0.02);
  border: 1px solid var(--divider-color, rgba(0,0,0,0.08));
  border-radius: 16px;
  padding: 8px 16px 8px 10px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.member-avatar-pill:hover {
  background: rgba(2, 136, 209, 0.06);
  transform: translateY(-2px);
  border-color: var(--primary-color, #0288d1);
}

.avatar-wrapper {
  position: relative;
  width: 52px;
  height: 52px;
  flex-shrink: 0;
}

.avatar-wrapper.avatar-lg {
  width: 80px;
  height: 80px;
}

.avatar-wrapper.avatar-sm {
  width: 38px;
  height: 38px;
}

.avatar-circle {
  width: 100%;
  height: 100%;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  position: relative;
  background: var(--card-background-color, #ffffff);
  box-shadow: 0 3px 10px rgba(0,0,0,0.12);
  border: 2px solid var(--divider-color, rgba(0,0,0,0.08));
}

.avatar-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 50%;
  display: block;
}

.avatar-fallback {
  font-size: 20px;
  font-weight: 700;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}

.avatar-circle.avatar-dad {
  background: linear-gradient(135deg, #0288d1 0%, #26c6da 100%);
}

.avatar-circle.avatar-mom {
  background: linear-gradient(135deg, #ec4899 0%, #f43f5e 100%);
}

.avatar-circle.avatar-milena {
  background: linear-gradient(135deg, #8b5cf6 0%, #a855f7 100%);
}

.avatar-circle.avatar-artem {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
}

.online-dot {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #22c55e;
  border: 2.5px solid var(--card-background-color, #ffffff);
  z-index: 2;
}

.online-dot.in-school {
  background: #0288d1;
}

.online-dot.home {
  background: #10b981;
}

.online-dot.offline {
  background: #94a3b8;
}

.crown-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  font-size: 16px;
  filter: drop-shadow(0 2px 4px rgba(0,0,0,0.25));
  z-index: 3;
}

.wizard-illustration-box {
  text-align: center;
  margin: 10px 0 24px;
}

.wizard-illustration-img {
  max-width: 240px;
  width: 100%;
  height: auto;
  border-radius: 20px;
  filter: drop-shadow(0 12px 28px rgba(0,0,0,0.15));
}

.chip-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 6px;
}

.interactive-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: rgba(2, 136, 209, 0.08);
  color: var(--primary-color, #0288d1);
  border: 1px solid rgba(2, 136, 209, 0.25);
  border-radius: 20px;
  font-size: 13px;
  font-weight: 500;
}

.interactive-chip .chip-remove {
  cursor: pointer;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(0,0,0,0.12);
  color: var(--primary-text-color, #1e293b);
  font-size: 12px;
  line-height: 1;
  transition: all 0.15s;
}

.interactive-chip .chip-remove:hover {
  background: #ef4444;
  color: #fff;
}

.chip-add-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: var(--card-background-color, #ffffff);
  border: 1px dashed var(--divider-color, rgba(0,0,0,0.2));
  border-radius: 20px;
  font-size: 13px;
  color: var(--secondary-text-color, #64748b);
  cursor: pointer;
  transition: all 0.15s;
}

.chip-add-btn:hover {
  border-color: var(--primary-color, #0288d1);
  color: var(--primary-color, #0288d1);
}

.kpi-card {
  background: var(--card-background-color, #ffffff);
  border: 1px solid var(--divider-color, rgba(0,0,0,0.08));
  border-radius: 18px;
  padding: 16px 18px;
  display: flex;
  align-items: flex-start;
  gap: 14px;
  box-shadow: 0 2px 10px rgba(0,0,0,0.03);
  transition: transform 0.2s, box-shadow 0.2s;
}

.kpi-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(0,0,0,0.06);
}

.kpi-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
}

.kpi-content {
  flex: 1;
  min-width: 0;
}

.kpi-title {
  font-size: 13px;
  color: var(--secondary-text-color, #64748b);
  font-weight: 500;
  margin: 0 0 2px;
}

.kpi-value {
  font-size: 17px;
  font-weight: 700;
  margin: 0 0 4px;
}

.kpi-subtitle {
  font-size: 12px;
  color: var(--secondary-text-color, #94a3b8);
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.action-tile {
  background: var(--card-background-color, #ffffff);
  border: 1px solid var(--divider-color, rgba(0,0,0,0.08));
  border-radius: 18px;
  padding: 18px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 10px;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgba(0,0,0,0.03);
}

.action-tile:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.08);
  border-color: var(--primary-color, #0288d1);
}

.action-tile-icon {
  width: 48px;
  height: 48px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
}

.action-tile-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--primary-text-color, #1e293b);
}

.mobile-bottom-nav {
  display: none;
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  background: var(--card-background-color, #ffffff);
  border-top: 1px solid var(--divider-color, rgba(0,0,0,0.1));
  padding: 8px 12px;
  z-index: 100;
  box-shadow: 0 -4px 20px rgba(0,0,0,0.08);
}

@media (max-width: 768px) {
  .mobile-bottom-nav {
    display: flex;
    justify-content: space-around;
    align-items: center;
  }
  .nav-tabs-bar {
    display: none;
  }
  .panel-container {
    padding-bottom: 90px;
  }
}

.bottom-nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--secondary-text-color, #64748b);
  cursor: pointer;
  padding: 4px 10px;
  border-radius: 10px;
  transition: color 0.15s;
}

.bottom-nav-item.active {
  color: var(--primary-color, #0288d1);
}

.bottom-nav-item .icon {
  font-size: 20px;
}
  border: 2.5px solid var(--card-background-color, #ffffff);
}

.online-dot.in-school {
  background: #0288d1;
}

.member-meta h5 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 4px;
}

.member-meta p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--secondary-text-color, #64748b);
  display: flex;
  align-items: center;
  gap: 4px;
}

.add-member-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 2px dashed var(--divider-color, rgba(0,0,0,0.2));
  border-radius: 16px;
  padding: 10px 18px;
  background: transparent;
  color: var(--secondary-text-color, #64748b);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.add-member-pill:hover {
  border-color: var(--primary-color, #0288d1);
  color: var(--primary-color, #0288d1);
  background: rgba(2, 136, 209, 0.05);
}

.hero-quote-card {
  background: linear-gradient(135deg, rgba(2, 136, 209, 0.08) 0%, rgba(0, 180, 216, 0.04) 100%);
  border: 1px solid rgba(2, 136, 209, 0.2);
  border-radius: 16px;
  padding: 12px 18px;
  font-size: 13px;
  font-style: italic;
  color: #0288d1;
  display: flex;
  align-items: center;
  gap: 10px;
}

/* ================= 3-COLUMN OVERVIEW (Ref 2) ================= */
.status-pill-card {
  background: var(--card-background-color, #ffffff);
  border-radius: 16px;
  padding: 16px 18px;
  border: 1px solid var(--divider-color, rgba(0,0,0,0.08));
  display: flex;
  flex-direction: column;
  gap: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 8px rgba(0,0,0,0.03);
}

.status-pill-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 18px rgba(0,0,0,0.08);
  border-color: rgba(2, 136, 209, 0.35);
}

.status-pill-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.status-icon-box {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
}

.icon-tg { background: rgba(2, 136, 209, 0.12); color: #0288d1; }
.icon-ai { background: rgba(168, 85, 247, 0.12); color: #9333ea; }
.icon-school { background: rgba(34, 197, 94, 0.12); color: #16a34a; }
.icon-court { background: rgba(245, 158, 11, 0.12); color: #d97706; }
.icon-pantry { background: rgba(244, 63, 94, 0.12); color: #e11d48; }
.icon-maint { background: rgba(14, 165, 233, 0.12); color: #0284c7; }

.status-pill-card h4 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
}

.status-pill-card p {
  margin: 0;
  font-size: 12px;
  color: var(--secondary-text-color, #64748b);
}

/* ================= QUICK ACTIONS 4-TILE ROW (Ref 2) ================= */
.quick-action-tile {
  background: var(--card-background-color, #ffffff);
  border: 1px solid var(--divider-color, rgba(0,0,0,0.08));
  border-radius: 16px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 2px 6px rgba(0,0,0,0.03);
}

.quick-action-tile:hover {
  transform: translateY(-3px);
  box-shadow: 0 6px 16px rgba(0,0,0,0.08);
  border-color: var(--primary-color, #0288d1);
}

.quick-action-tile .tile-icon {
  width: 46px;
  height: 46px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
}

.quick-action-tile span.label {
  font-size: 13px;
  font-weight: 700;
}

/* ================= EVENTS & TODAY'S CHECKLIST (Ref 4) ================= */
.event-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--divider-color, rgba(0,0,0,0.06));
}

.event-item:last-child {
  border-bottom: none;
}

.event-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.event-time {
  font-size: 12px;
  color: var(--secondary-text-color, #94a3b8);
  font-family: monospace;
}

.event-actor {
  font-size: 13px;
  font-weight: 700;
}

.score-chip {
  padding: 3px 8px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 700;
}

.score-plus {
  background: #e8f5e9;
  color: #2e7d32;
}

.score-minus {
  background: #ffebee;
  color: #c62828;
}

.score-info {
  background: #e1f5fe;
  color: #0288d1;
}

.event-text {
  font-size: 13px;
  color: var(--primary-text-color, #1e293b);
}

.task-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 11px 14px;
  border-radius: 12px;
  background: rgba(0,0,0,0.02);
  margin-bottom: 8px;
  cursor: pointer;
  transition: background 0.15s;
}

.task-item:hover {
  background: rgba(2, 136, 209, 0.05);
}

.task-checkbox-label {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  font-weight: 500;
}

.task-checkbox-label input[type="checkbox"] {
  width: 18px;
  height: 18px;
  cursor: pointer;
  accent-color: #0288d1;
}

/* ================= ATTENTION BLOCK (Ref 2, 4) ================= */
.attention-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 18px;
  border-radius: 14px;
  background: #fff8e1;
  border: 1px solid #ffe082;
  margin-bottom: 10px;
}

.attention-row.danger {
  background: #ffebee;
  border-color: #ffcdd2;
}

.attention-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.attention-left .icon {
  font-size: 22px;
}

.attention-left strong {
  font-size: 14px;
  font-weight: 700;
}

.attention-left p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--secondary-text-color, #64748b);
}

/* ================= BADGES ================= */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.2px;
}

.badge-success { background: #e8f5e9; color: #2e7d32; }
.badge-warning { background: #fff3e0; color: #ef6c00; }
.badge-danger  { background: #ffebee; color: #c62828; }
.badge-info    { background: #e1f5fe; color: #0288d1; }
.badge-purple  { background: #f3e5f5; color: #7b1fa2; }

/* ================= BUTTONS ================= */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  border: none;
  transition: all 0.15s ease-in-out;
  white-space: nowrap;
}

.btn-primary {
  background: linear-gradient(135deg, #0288d1 0%, #00b4d8 100%);
  color: #ffffff;
  box-shadow: 0 2px 8px rgba(2, 136, 209, 0.25);
}

.btn-primary:hover {
  box-shadow: 0 4px 14px rgba(2, 136, 209, 0.4);
  transform: translateY(-1px);
}

.btn-secondary {
  background: rgba(0,0,0,0.05);
  color: var(--primary-text-color, #1e293b);
  border: 1px solid var(--divider-color, rgba(0,0,0,0.1));
}

.btn-secondary:hover {
  background: rgba(0,0,0,0.09);
}

.btn-sm {
  padding: 6px 12px;
  font-size: 12px;
  border-radius: 10px;
}

.btn-danger {
  background: #ffebee;
  color: #c62828;
  border: 1px solid #ffcdd2;
}

.btn-danger:hover {
  background: #ffcdd2;
}

/* ================= CHIPS ================= */
.chips-container {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 6px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: rgba(0,0,0,0.04);
  border: 1px solid var(--divider-color, rgba(0,0,0,0.12));
  padding: 5px 12px;
  border-radius: 16px;
  font-size: 12px;
  font-weight: 600;
}

.chip .chip-remove {
  cursor: pointer;
  color: var(--secondary-text-color, #94a3b8);
  font-size: 14px;
}

.chip .chip-remove:hover {
  color: #c62828;
}

/* ================= FORMS ================= */
.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 6px;
  color: var(--primary-text-color, #1e293b);
}

.form-control {
  width: 100%;
  padding: 10px 14px;
  border-radius: 12px;
  border: 1px solid var(--divider-color, rgba(0,0,0,0.15));
  background: var(--card-background-color, #ffffff);
  color: var(--primary-text-color, #1e293b);
  font-size: 14px;
  outline: none;
  transition: border-color 0.15s;
}

.form-control:focus {
  border-color: var(--primary-color, #0288d1);
}

/* ================= SWITCH & SLIDER ================= */
.toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
}

.switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  top: 0; left: 0; right: 0; bottom: 0;
  background-color: #cbd5e1;
  transition: .2s;
  border-radius: 24px;
}

.slider:before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  transition: .2s;
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0,0,0,0.2);
}

input:checked + .slider {
  background-color: #0288d1;
}

input:checked + .slider:before {
  transform: translateX(20px);
}

/* ================= SCHOOL PREVIEW CARD (Ref 4, Screen 5) ================= */
.school-preview-box {
  background: #fffde7;
  border: 1px solid #fff59d;
  border-radius: 16px;
  padding: 18px;
}

.school-preview-box h5 {
  margin: 0 0 10px 0;
  font-size: 14px;
  font-weight: 700;
  color: #f57f17;
  display: flex;
  align-items: center;
  gap: 6px;
}

.school-preview-box ul {
  margin: 0 0 12px 0;
  padding-left: 18px;
  font-size: 13px;
  color: #374151;
  line-height: 1.6;
}

.school-preview-box .meta-note {
  font-size: 12px;
  color: #6b7280;
}

/* ================= DEDICATED MODULE PAGE VIEW ================= */
.module-view-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  gap: 16px;
  flex-wrap: wrap;
}

.module-title-area {
  display: flex;
  align-items: center;
  gap: 14px;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 12px;
  background: rgba(0,0,0,0.05);
  border: 1px solid var(--divider-color, rgba(0,0,0,0.1));
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  color: var(--primary-text-color, #1e293b);
  transition: all 0.15s;
}

.back-btn:hover {
  background: rgba(0,0,0,0.08);
}

/* ================= MODALS ================= */
.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  padding: 20px;
}

.modal-content {
  background: var(--card-background-color, #ffffff);
  border-radius: 20px;
  border: 1px solid var(--divider-color, rgba(0,0,0,0.1));
  box-shadow: 0 20px 50px rgba(0,0,0,0.25);
  width: 680px;
  max-width: 100%;
  max-height: 90vh;
  overflow-y: auto;
  padding: 24px;
}

/* ================= RESPONSIVE ================= */
@media (max-width: 900px) {
  .panel-container {
    padding: 12px 14px 60px;
  }
  .grid-cols-4, .grid-cols-3, .grid-cols-2 {
    grid-template-columns: 1fr;
  }
  .family-hero-card {
    flex-direction: column;
    align-items: flex-start;
  }
  .header {
    flex-direction: column;
    align-items: flex-start;
  }
  .header-right {
    width: 100%;
    justify-content: space-between;
  }
  .search-box {
    max-width: 100%;
    width: 100%;
  }
}
/* Live control-center components. All text colors inherit the selected HA theme. */
.panel-stack {display:flex;flex-direction:column;gap:20px;min-width:0}
.panel-container {max-width:1280px;overflow-wrap:anywhere}
.panel-container :is(section,form,.grid,.grid>*,.header-brand,.header-right) {min-width:0}
.panel-container h3 {margin:0 0 16px;font-size:18px;line-height:1.35}
.panel-container h4 {margin:12px 0}
.panel-container p {line-height:1.5}
.panel-muted {color:var(--secondary-text-color,#64748b);line-height:1.5;display:block}
.panel-actions {display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:16px}
.panel-notice {padding:14px 18px;margin:0 0 16px;border:1px solid var(--primary-color,#0288d1);border-radius:12px;background:var(--card-background-color,#fff)}
.panel-error {border-color:var(--error-color,#db4437)}
.nav-tabs-bar {display:flex;gap:4px;border-bottom:1px solid var(--divider-color,#d8e0ea);margin-bottom:22px;overflow-x:auto}
.nav-tab-item {background:transparent;border:0;border-bottom:3px solid transparent;padding:14px 18px;color:var(--secondary-text-color,#64748b);font:inherit;white-space:nowrap;cursor:pointer}
.nav-tab-item.active {border-color:var(--primary-color,#0288d1);color:var(--primary-color,#0288d1);font-weight:700}
.panel-members-strip {display:flex;flex-wrap:wrap;gap:14px}
.panel-members-grid {grid-template-columns:repeat(auto-fill,minmax(160px,1fr))}
.panel-member-card {display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;border:1px solid var(--divider-color,#d8e0ea);background:var(--primary-background-color,#f4f6f9);color:var(--primary-text-color,#1e293b);border-radius:16px;min-width:120px;padding:18px 12px;font:inherit;cursor:pointer}
.panel-member-card:hover {border-color:var(--primary-color,#0288d1)}
.panel-add-member {border-style:dashed;color:var(--primary-color,#0288d1)}
.panel-avatar {height:62px;width:62px;flex:0 0 62px;border-radius:50%;display:grid;place-items:center;background:color-mix(in srgb,var(--primary-color,#0288d1) 12%,var(--card-background-color,#fff));color:var(--primary-text-color,#1e293b);font-size:24px;font-weight:700}
.panel-quick-grid {display:grid;grid-template-columns:1fr 1fr;gap:10px}
.panel-quick-grid .btn {white-space:normal;min-height:86px}
.panel-status-row {display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 0;flex-wrap:wrap;border-bottom:1px solid var(--divider-color,#d8e0ea)}
.panel-status-row strong {font-size:13px}
.panel-issue {display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:12px 0}
.panel-module-card {display:flex;flex-direction:column;gap:4px}
.panel-module-card .btn {align-self:flex-start;margin-top:auto}
.panel-subtabs {display:flex;gap:10px;flex-wrap:wrap}
.panel-subtabs .active {border-color:var(--primary-color,#0288d1);color:var(--primary-color,#0288d1)}
.panel-search-result {display:flex;flex-direction:column;align-items:flex-start;gap:8px;width:100%;padding:16px;margin:10px 0;text-align:left;font:inherit;background:var(--primary-background-color,#f4f6f9);color:var(--primary-text-color,#1e293b);border:1px solid var(--divider-color,#d8e0ea);border-radius:12px;cursor:pointer}
.panel-toggle {display:flex;align-items:center;gap:10px;font-weight:600}
.panel-container input[type=checkbox] {width:22px;height:22px;accent-color:var(--primary-color,#0288d1)}
.panel-container .form-control {min-height:44px;width:100%;max-width:100%;font:inherit;color:var(--primary-text-color,#1e293b);background:var(--card-background-color,#fff)}
.panel-container .form-group {display:flex;flex-direction:column;gap:7px;margin-bottom:18px;min-width:0}
.panel-container .form-group input[type=checkbox] {width:22px;min-height:22px}
.panel-container textarea {min-height:100px;resize:vertical}
.panel-container .btn {min-height:44px;max-width:100%;white-space:normal;text-decoration:none;text-align:center;line-height:1.4}
.panel-container .btn:disabled,.panel-container button:disabled {opacity:.55;cursor:default}
.panel-container :is(button,a,input,select,textarea,summary):focus-visible {outline:3px solid var(--primary-color,#0288d1);outline-offset:3px}
.panel-wizard-steps {display:grid;grid-template-columns:repeat(4,1fr);list-style:none;gap:10px;padding:0;margin:8px 0}
.panel-wizard-steps li {font-size:13px;color:var(--secondary-text-color,#64748b);border-top:4px solid var(--divider-color,#d8e0ea);padding-top:12px}
.panel-wizard-steps .active {color:var(--primary-color,#0288d1);border-color:var(--primary-color,#0288d1);font-weight:700}
.panel-workspace {min-width:0;--ha-card-background:var(--card-background-color,#fff)}
.panel-container .mobile-bottom-nav {background:var(--card-background-color,#fff);border-color:var(--divider-color,#d8e0ea)}
.panel-container .bottom-nav-item {display:flex;flex-direction:column;justify-content:center;align-items:center;gap:5px;border:0;background:transparent;font:inherit;color:var(--secondary-text-color,#64748b);min-height:64px;padding:8px 4px;flex:1;font-size:11px;overflow-wrap:normal}
.panel-nav-icon {font-size:18px}
.panel-enrollment-consent {display:flex;align-items:flex-start;gap:12px;line-height:1.5;margin:18px 0}
.panel-enrollment-consent input {flex:0 0 22px}
.panel-container :is(input,select,textarea,button) {scroll-margin-bottom:100px}
.panel-container .bottom-nav-item.active {color:var(--primary-color,#0288d1)}
@media(max-width:700px){
  .panel-container {padding:14px 12px 90px}
  .header-brand h1 {font-size:21px}
  .header-right {gap:10px}
  .search-box {min-width:0}
  .nav-tabs-bar {display:none}
  .panel-container .card {padding:18px 16px}
  .panel-members-strip {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
  .panel-member-card {min-width:0}
  .panel-wizard-steps {grid-template-columns:repeat(2,1fr)}
  .panel-status-row .btn {flex-basis:100%}
  .modal-overlay {padding:12px}
  .modal-content {padding:20px}
}
`;
