# Channels & Devices Domain

## Overview

Manages digital signage channels, device types, capability profiles, physical devices, logical carriers, and display surfaces.

## Tables

| Table | Description |
|-------|-------------|
| `channels` | Digital signage channel (KSO, Android TV, ESL, etc.) |
| `device_types` | Type of device within a channel |
| `capability_profiles` | Display capabilities (resolution, formats, proof type) |
| `physical_devices` | Physical device instance in a store |
| `logical_carriers` | Logical screen zone on a device |
| `display_surfaces` | Rendered display area with capability profile |

## Seed

```bash
cd backend
python -m app.domains.channels.seed
```

Creates 5 channels: `kso`, `android_tv`, `price_checker`, `esl`, `led_shelf_banner`.

## API

### Channels
| Method | Path | Permission |
|--------|------|------------|
| GET | `/api/channels` | channels.read |
| POST | `/api/channels` | channels.manage |

### Device Types
| Method | Path | Permission |
|--------|------|------------|
| GET | `/api/device-types?channel_id=` | devices.read |
| POST | `/api/device-types` | devices.manage |

### Capability Profiles
| Method | Path | Permission |
|--------|------|------------|
| GET | `/api/capability-profiles?device_type_id=` | devices.read |
| POST | `/api/capability-profiles` | devices.manage |

### Physical Devices
| Method | Path | Permission |
|--------|------|------------|
| GET | `/api/physical-devices?store_id=&device_type_id=&status=` | devices.read |
| POST | `/api/physical-devices` | devices.manage |

### Logical Carriers
| Method | Path | Permission |
|--------|------|------------|
| GET | `/api/logical-carriers?physical_device_id=` | devices.read |
| POST | `/api/logical-carriers` | devices.manage |

### Display Surfaces
| Method | Path | Permission |
|--------|------|------------|
| GET | `/api/display-surfaces?logical_carrier_id=` | devices.read |
| POST | `/api/display-surfaces` | devices.manage |
