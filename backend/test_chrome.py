from selenium import webdriver


def main():
    driver = webdriver.Chrome()
    try:
        driver.get("https://www.amazon.com")
        input("Press Enter to exit...")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
