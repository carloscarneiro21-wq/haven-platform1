import { createContext, useContext, useState } from "react";

const SidebarContext = createContext(null);

export const useSidebar = () => {
  const context = useContext(SidebarContext);
  if (!context) {
    throw new Error("useSidebar must be used within a SidebarProvider");
  }
  return context;
};

export const SidebarProvider = ({ children }) => {
  const [isExpanded, setIsExpanded] = useState(true);

  const toggle = () => setIsExpanded(prev => !prev);
  const expand = () => setIsExpanded(true);
  const collapse = () => setIsExpanded(false);

  const value = {
    isExpanded,
    toggle,
    expand,
    collapse,
  };

  return (
    <SidebarContext.Provider value={value}>
      {children}
    </SidebarContext.Provider>
  );
};

export default SidebarContext;
