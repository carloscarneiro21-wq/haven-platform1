import * as React from "react";
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/drawer";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";

export function HelpDrawer({ open, onClose, title, children }) {
  return (
    <Drawer open={open} onOpenChange={onClose}>
      <DrawerContent className="bg-zinc-900 border-zinc-800 max-h-[85vh]">
        <div className="mx-auto w-full max-w-3xl">
          <DrawerHeader className="text-left">
            <div className="flex items-center justify-between">
              <DrawerTitle className="text-xl font-rajdhani text-white">{title}</DrawerTitle>
              <DrawerClose asChild>
                <Button variant="ghost" size="icon" className="text-zinc-400 hover:text-white">
                  <X className="w-5 h-5" />
                </Button>
              </DrawerClose>
            </div>
          </DrawerHeader>
          <div className="px-4 pb-6 overflow-y-auto max-h-[60vh]">
            <div className="prose prose-invert prose-sm max-w-none">
              {children}
            </div>
          </div>
          <DrawerFooter className="pt-2 border-t border-zinc-800">
            <DrawerClose asChild>
              <Button variant="outline" className="w-full">Fechar</Button>
            </DrawerClose>
          </DrawerFooter>
        </div>
      </DrawerContent>
    </Drawer>
  );
}

export default HelpDrawer;
