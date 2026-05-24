import { useEffect, useState } from "react";

export interface MarketStatus {
  isOpen: boolean;
  label: string;
  session: "pre-market" | "live" | "close";
}

function getMarketStatus(): MarketStatus {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour: "numeric",
    minute: "numeric",
    weekday: "short",
    hour12: false,
  }).formatToParts(new Date());

  const valueOf = (type: string) =>
    parts.find((part) => part.type === type)?.value ?? "";

  const weekday = valueOf("weekday");
  const hour = Number.parseInt(valueOf("hour"), 10);
  const minute = Number.parseInt(valueOf("minute"), 10);
  const timeValue = hour * 60 + minute;

  if (weekday === "Sat" || weekday === "Sun") {
    return { isOpen: false, label: "Closed", session: "close" };
  }

  const preMarket = 4 * 60;
  const open = 9 * 60 + 30;
  const close = 16 * 60;
  const afterHours = 20 * 60;

  if (timeValue >= open && timeValue < close) {
    return { isOpen: true, label: "Open", session: "live" };
  }

  if (timeValue >= preMarket && timeValue < open) {
    return { isOpen: false, label: "Pre-Market", session: "pre-market" };
  }

  if (timeValue >= close && timeValue < afterHours) {
    return { isOpen: false, label: "After-Hours", session: "close" };
  }

  return { isOpen: false, label: "Closed", session: "close" };
}

export function useMarketStatus(): MarketStatus {
  const [status, setStatus] = useState<MarketStatus>(getMarketStatus);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setStatus(getMarketStatus());
    }, 60_000);

    return () => window.clearInterval(timer);
  }, []);

  return status;
}
