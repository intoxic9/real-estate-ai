"use client";

import { MapContainer, Marker, Popup, TileLayer } from "react-leaflet";
import L from "leaflet";

type ForeclosureMapItem = {
  id: string;
  address: string;
  status: string;
  estimated_value_usd?: number | null;
};

const markerIcon = new L.Icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});
const AnyMapContainer = MapContainer as any;
const AnyTileLayer = TileLayer as any;
const AnyMarker = Marker as any;
const AnyPopup = Popup as any;

function money(v?: number | null) {
  if (v == null) return "N/A";
  return `$${Math.round(v).toLocaleString()}`;
}

export default function ForeclosuresMap({ items }: { items: ForeclosureMapItem[] }) {
  return (
    <AnyMapContainer center={[40.7128, -74.006]} zoom={8} style={{ height: "100%", width: "100%" }}>
      <AnyTileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution="&copy; OpenStreetMap contributors"
      />
      {items.slice(0, 50).map((item, idx) => (
        <AnyMarker
          key={item.id}
          position={[40.7128 + (idx % 8) * 0.03, -74.006 + (idx % 8) * 0.03]}
          icon={markerIcon}
        >
          <AnyPopup>
            <div className="text-xs">
              <p className="font-semibold">{item.address}</p>
              <p>{item.status}</p>
              <p>{money(item.estimated_value_usd)}</p>
            </div>
          </AnyPopup>
        </AnyMarker>
      ))}
    </AnyMapContainer>
  );
}

