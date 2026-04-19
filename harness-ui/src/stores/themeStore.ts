import { create } from "zustand";
import { persist } from "zustand/middleware";
import { PaletteMode } from "@mui/material";

interface ThemeState {
  mode: PaletteMode;
  primaryColor: string;
  setMode: (mode: PaletteMode) => void;
  setPrimaryColor: (color: string) => void;
  toggleMode: () => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      mode: "dark",
      primaryColor: "#7c6af7",
      setMode: (mode) => set({ mode }),
      setPrimaryColor: (primaryColor) => set({ primaryColor }),
      toggleMode: () =>
        set({ mode: get().mode === "dark" ? "light" : "dark" }),
    }),
    { name: "vloop-theme" }
  )
);
