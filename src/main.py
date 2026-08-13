from .demo import print_demo_result, run_demo


def main() -> None:
    """Запустить демонстрацию банковской системы."""
    # Создаём клиентов, счета, транзакции и отчёты.
    result = run_demo()

    # Показываем итог работы в консоли.
    print_demo_result(*result)


if __name__ == "__main__":
    main()
