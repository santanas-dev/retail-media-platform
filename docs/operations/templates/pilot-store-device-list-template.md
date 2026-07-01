# Pilot Store & Device List Template

**Version:** 1.0 | **Date:** ____-__-__ | **Owner:** Ops Team

> **IMPORTANT:** This template is a **placeholder** — fill in before pilot.  
> Pilot starts ONLY from approved list. No wildcard "all stores".  
> Max initial scope: **1 store / 1–5 devices**. Every device must have rollback path.

---

## Rules

1. Pilot starts only from this approved list — **no wildcard "all stores"**
2. Max initial scope: **1 store / 1–5 devices**
3. Every device must have a documented **rollback path**
4. Approval required: **Business Owner + Security Owner + Ops Owner**
5. Store must have on-site contact available during pilot window
6. Legacy manifest route must remain active as fallback

---

## Pilot Entry

### General

| Field | Value |
|---|---|
| **Pilot ID** | `PILOT-____` |
| **Pilot Name** | ______________ |
| **Pilot Window** | ____-__-__ to ____-__-__ |
| **Business Owner** | ______________ (email: ________) |
| **Security Owner** | ______________ (email: ________) |
| **Ops Owner** | ______________ (email: ________) |
| **Rollback Owner** | ______________ (phone: ________) |

---

## Store

| Field | Value |
|---|---|
| **Store Code** | `____________` |
| **Store Name** | ______________ |
| **Store Address** | ______________ |
| **Region** | ____________ (e.g. Центральный, С-З) |
| **Network Segment** | ____________ (wired / wifi SSID: ____) |
| **Contact on Site** | ______________ (phone: ________) |

---

## Device #1 (primary)

| Field | Value |
|---|---|
| **Device Code** | `____________` |
| **Physical Device ID** | `<UUID placeholder>` |
| **Gateway Device ID** | `<UUID placeholder>` |
| **Channel Code** | `kso` |
| **Device Type** | KSO (UKM5) |
| **Screen Resolution** | `768 × 1024` px |
| **Orientation** | Portrait |
| **Software Version** | `0.1.0` |
| **Rollback Path** | Legacy KSO manifest (route: `/api/legacy/kso/manifest`) |
| **Rollback Verified** | ⬜ Yes / ⬜ No |
| **Approval Status** | ⬜ Pending / ⬜ Approved / ⬜ Rejected |
| **Pilot Status** | ⬜ Registered / ⬜ Onboarded / ⬜ Active / ⬜ Rolled back / ⬜ Completed |

---

## Device #2 (optional, up to 5)

| Field | Value |
|---|---|
| **Device Code** | `____________` |
| **Physical Device ID** | `<UUID placeholder>` |
| **Gateway Device ID** | `<UUID placeholder>` |
| **Channel Code** | `kso` |
| **Device Type** | KSO (UKM5) |
| **Screen Resolution** | `____ × ____` px |
| **Orientation** | Portrait / Landscape |
| **Software Version** | `0.1.0` |
| **Rollback Path** | Legacy KSO manifest |
| **Rollback Verified** | ⬜ Yes / ⬜ No |
| **Approval Status** | ⬜ Pending / ⬜ Approved / ⬜ Rejected |
| **Pilot Status** | ⬜ Registered / ⬜ Onboarded / ⬜ Active / ⬜ Rolled back / ⬜ Completed |

---

## Pre-Pilot Verification Checklist

| # | Check | Device 1 | Device 2 | Device 3 | Device 4 | Device 5 |
|---|---|---|---|---|---|---|
| V1 | Device registered in Gateway | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| V2 | Heartbeat visible | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| V3 | Rollback path documented | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| V4 | On-site contact confirmed | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| V5 | Network connectivity tested | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| V6 | Legacy mode verified | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| V7 | KSO physical playback test passed | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |

---

## Approval Sign-Off

| Role | Name | Date | Signature |
|---|---|---|---|
| Business Owner | ______________ | __-__-__ | ________ |
| Security Owner | ______________ | __-__-__ | ________ |
| Ops Owner | ______________ | __-__-__ | ________ |

---

## Pilot Completion

| Field | Value |
|---|---|
| **Pilot End Date** | ____-__-__ |
| **Outcome** | ⬜ Success / ⬜ Partial / ⬜ Failed |
| **Issues Found** | ______________ |
| **Rollback Performed** | ⬜ Yes / ⬜ No |
| **Go for Expansion** | ⬜ Yes / ⬜ No |
| **Expansion Scope** | ______________ |
