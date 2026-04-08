export const staggerContainer = {
  animate: { transition: { staggerChildren: 0.05 } },
}

export const staggerContainerFast = {
  animate: { transition: { staggerChildren: 0.03 } },
}

export const staggerItem = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
}

export const staggerItemSmall = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
}

export const fadeInUp = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.2 },
}
