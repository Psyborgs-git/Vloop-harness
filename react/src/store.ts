import { create } from 'zustand';

interface RouteStore {
    versions: Record<string, number>;
    updateVersion: (path: string, version: number) => void;
}

export const useRouteStore = create<RouteStore>((set) => ({
    versions: {},
    updateVersion: (path: string, version: number) =>
        set((state) => ({
            versions: {
                ...state.versions,
                [path]: version
            }
        }))
}));
