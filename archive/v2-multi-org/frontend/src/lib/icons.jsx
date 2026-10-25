/**
 * Curated icon set that a user can assign to each tracked radio. Uses
 * lucide-react (already installed) so the icons are crisp on the map and stay
 * consistent with the rest of the UI. Emoji is explicitly avoided per design
 * guidelines.
 */
import {
  Radio,
  Truck,
  Car,
  Bike,
  User as UserIcon,
  Users,
  Ship,
  Plane,
  HardHat,
  Shield,
  Ambulance,
  Anchor,
  MapPin,
  Bus,
  Rocket,
  Flame,
  Cog,
  Cpu,
} from "lucide-react";

export const ICON_SET = [
  { key: "Radio", Icon: Radio, label: "Radio" },
  { key: "User", Icon: UserIcon, label: "Person" },
  { key: "Users", Icon: Users, label: "Team" },
  { key: "Truck", Icon: Truck, label: "Truck" },
  { key: "Car", Icon: Car, label: "Car" },
  { key: "Bus", Icon: Bus, label: "Bus" },
  { key: "Bike", Icon: Bike, label: "Bike" },
  { key: "Ship", Icon: Ship, label: "Boat" },
  { key: "Anchor", Icon: Anchor, label: "Anchor" },
  { key: "Plane", Icon: Plane, label: "Plane" },
  { key: "HardHat", Icon: HardHat, label: "Crew" },
  { key: "Shield", Icon: Shield, label: "Security" },
  { key: "Ambulance", Icon: Ambulance, label: "EMS" },
  { key: "Flame", Icon: Flame, label: "Fire" },
  { key: "Rocket", Icon: Rocket, label: "Rocket" },
  { key: "MapPin", Icon: MapPin, label: "Pin" },
  { key: "Cog", Icon: Cog, label: "Ops" },
  { key: "Cpu", Icon: Cpu, label: "Tech" },
];

const KEY_MAP = Object.fromEntries(ICON_SET.map((i) => [i.key, i.Icon]));

export function iconFor(key) {
  return KEY_MAP[key] || Radio;
}

export const COLOR_SET = [
  { key: "#39ff14", label: "Radar" },
  { key: "#00f0ff", label: "Cyan" },
  { key: "#ffb800", label: "Amber" },
  { key: "#ff3b30", label: "Red" },
  { key: "#c084fc", label: "Violet" },
  { key: "#f472b6", label: "Pink" },
  { key: "#f3f4f6", label: "White" },
];
