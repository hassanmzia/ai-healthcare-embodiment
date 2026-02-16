import { create } from 'zustand';
import type { DashboardData, WorkflowRun, Notification } from '../types';

interface AppState {
  // Dashboard
  dashboard: DashboardData | null;
  dashboardLoading: boolean;
  setDashboard: (data: DashboardData) => void;
  setDashboardLoading: (loading: boolean) => void;

  // Active workflow run
  activeRunId: string | null;
  setActiveRunId: (id: string | null) => void;

  // Notifications
  notifications: Notification[];
  unreadCount: number;
  setNotifications: (notifications: Notification[]) => void;
  setUnreadCount: (count: number) => void;

  // Theme
  darkMode: boolean;
  toggleDarkMode: () => void;

  // Sidebar
  sidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  dashboard: null,
  dashboardLoading: false,
  setDashboard: (data) => set({ dashboard: data }),
  setDashboardLoading: (loading) => set({ dashboardLoading: loading }),

  activeRunId: null,
  setActiveRunId: (id) => set({ activeRunId: id }),

  notifications: [],
  unreadCount: 0,
  setNotifications: (notifications) => set({ notifications }),
  setUnreadCount: (count) => set({ unreadCount: count }),

  darkMode: false,
  toggleDarkMode: () => set((state) => ({ darkMode: !state.darkMode })),

  sidebarOpen: typeof window !== 'undefined' && window.innerWidth < 900 ? false : true,
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
}));
